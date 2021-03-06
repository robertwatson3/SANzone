import argparse
import time
import os.path
import re
import getpass
from UcsSdk import *
from prettytable import PrettyTable

parser = argparse.ArgumentParser()
parser.add_argument('-i', '--input', 
	help="Input file containing list of hosts and HBA's in the format \"host_hba_name,hba_wwpn\"")
parser.add_argument('-o', '--output',
	default="MDS_Config-" + time.strftime("%H:%M-%m-%d-%Y") +".txt",
	help='Destination file for MDS configuration. Default is "MDS_Config-date.txt"')
parser.add_argument('-a', '--array', help="Array to zone HBA's to.")
parser.add_argument('-u', '--ucs', nargs='+', help="Hostname or IP address of UCS Managers separated by a space")
parser.add_argument('-l', '--login', help="Login for UCS Manager.")
parser.add_argument('-p', '--password', help="Password for UCS Manager.")
parser.add_argument('-s', '--serviceprofile', nargs='+', help="UCS Service Profile name wildcard. Multiple Service Profile names can be provided separated by a space, or simply putting a generic term like 'ESXi' would zone ALL Service Profiles that contain ESXi.")
parser.add_argument('-f', '--answerfile', help="File with all required options in the format: array = array1, ucs = 10.0.0.1, login = admin, serviceprofile = sp1")
args = parser.parse_args()

array = args.array
vsanA = 5
vsanB = 50
zonesetA = 'zoneset name PCloud-A vsan %s\n' % vsanA
zonesetB = 'zoneset name PCloud-B vsan %s\n' % vsanB

def create_hba_dict_from_ucs(ucs, login, password, service_profile_list):
    for attempt in range(3):        
        try:
            handle = UcsHandle()
            print "Connecting to UCS at %s as %s." % (ucs, login)
            if not password:
                password = getpass.getpass(prompt='UCS Password: ')
            handle.Login(ucs, username=login, password=password)
            print "Connection Successful"
            output = {}
            print "Getting HBA information"
            getRsp = handle.GetManagedObject(None, None,{"Dn":"org-root/"}) # Last part is a key value pair to filter for a specific MO
            moList = handle.GetManagedObject(getRsp, "vnicFc")
            for serviceprofile in service_profile_list: # Making an additional for loop to allow format "-s sp1 sp2" or regex like "-s sp[1,2]
                for mo in moList:
                    if str(mo.Addr) != 'derived': # Don't include Service Profile Templates
                            editedDn = str(mo.Dn)
                            #print editedDn
                            if serviceprofile in editedDn: # Check regex expression for match against cleaned up name
                                editedDn = re.sub('^((?:org-root.*)/ls-)+','',editedDn) #removes all org info up to SP name
                                editedDn = editedDn.replace(r'/fc','')
                                output[editedDn] = mo.Addr # Append key/value pair of any matched Dn's to output dictandle.Logout()
            return output
            break

        except Exception as err:
            if "Authentication failed" in str(err):
                print 'Authentication failed.'
                password = getpass.getpass(prompt='Please re-enter password for %s at UCS %s: ' % (login, ucs))
            else:
                print err.message
                print "Exception:", str(err)
                import traceback, sys
                print '-' * 60
                traceback.print_exc(file=sys.stdout)
                print '-' * 60
                break
    else:
        print "Connection failed. Skipping UCS %s." % ucs
        output = {}
        return output
def create_hba_dict_from_file(file):	
	host_hbas_string = open(file).read() # open(args.input).read()
	# split host_hbas_string into list
	host_hbas_list = host_hbas_string.split('\n')

	# break out hosts and HBA's into dict
	output = {}
	for line in host_hbas_list:
		key, val = line.split(',')
		output[key] = str(val)
	return output

def parse_answer_file(file):
    answerfile = open(file).read()
    answerfile = answerfile.split('\n')
    answers = {}
    for item in answerfile:
        if "ucs" in item.lower():
            ip_list = re.findall('((?:(?:[0-9]{1,3}.){3})[0-9]{1,3})', item) # RegEx to grab all IP addresses and return them as a list
            answers['ucs'] = ip_list
        elif "array" in item.lower():
            item = item.replace(' ', '')
            item = re.search('((?<==)\S*)', item) # Grab everything after the "=" sign
            answers['array'] = item.group()
        elif "login" in item.lower():
            item = item.replace(' ', '')
            item = re.search('((?<==)\S*)', item) # Grab everything after the "=" sign
            answers['login'] = item.group()
        elif "serviceprofile" in item.lower():
            item = re.search('((?<==).*)', item)
            ucs_list = item.group().split()
            answers['serviceprofile'] = ucs_list
        elif "vsana" in item.lower():
            item = re.search('([1-9]|(?:[0-9][0-9])|(?:[0-9][0-9][0-9])|(?:[1-4][0-9][0-9][0-4]))', item) # Huge regex to match VSAN 1-4094
            answers['vsanA'] = item.group()
        elif "vsanb" in item.lower():
            item = re.search('([1-9]|(?:[0-9][0-9])|(?:[0-9][0-9][0-9])|(?:[1-4][0-9][0-9][0-4]))', item) # Huge regex to match VSAN 1-4094
            answers['vsanB'] = item.group()
        elif "input" in item.lower():
            item = item.replace('input', '')
            item = item.replace('=', '')
            item = re.search('(\S.*(?<!(?:[ ]$)))', item) #RegEx to ignore leading and trailing spaces, and capture path and/or file name
    return answers
# Check that args are present/valid and then either create hba dict from file or UCS
if args.answerfile:
    answers = {}
    answers = parse_answer_file(args.answerfile)
    host_hbas = {}
    if not 'password' in answers:
        answers['password'] = getpass.getpass(prompt='UCS Password: ')
    for ucs in answers['ucs']:
        host_hbas.update(create_hba_dict_from_ucs(ucs, answers['login'], answers['password'], answers['serviceprofile']))
elif not (args.input or args.ucs):
    print 'HBA input file must be specified using -i option, or UCS must be specified using -u option. Use --help for more info.'
    quit(0)
elif args.ucs and not (args.login and args.serviceprofile): # removed "and args.password" from within parenthesis
	print "Login and service profile must be specified when using UCS as -l [login] -s [service profile]"
	quit(0)
elif (args.input and not os.path.isfile(args.input)):
	print 'Input file "%s" does not exist.' % args.input
	quit(0)
elif args.input:
	host_hbas = create_hba_dict_from_file(args.input)
elif args.ucs and args.login:
    if not args.password:
        args.password = getpass.getpass(prompt='UCS Password: ')
    host_hbas = {}
    for ucs in args.ucs:
	host_hbas.update(create_hba_dict_from_ucs(ucs, args.login, args.password, args.serviceprofile))

#Create fcalias
def create_fcalias(switch):
	output = '' # Create empty string that fcaliases will be appended too
	if switch == 'A':
		for host, hba in host_hbas.items():
			if host.endswith(switch): # Checks the end of each host for "A"
				output += "fcalias name %s vsan %d\nmember pwwn %s\n" % (host, vsanA, hba)
		return output
	elif switch == 'B':
		for host, hba in host_hbas.items():
			if host.endswith(switch): # Checks the end of each host for "B"
				output += "fcalias name %s vsan %d\nmember pwwn %s\n" % (host, vsanB, hba)
		return output
	else:
		print 'Valid switch parameter not provided to fcalias function.'

def create_zones(switch):
	output = '' # Create empty string that zones will be appended to
	global zonesetA # Use global variable, don't create local
	global zonesetB # Use global variable, don't create local
	if switch == 'A':
		for host in host_hbas.keys():
			if host.endswith(switch):
				zonesetA += "member %s_%s\n" % (host, array) # Add zone to zoneset
				output += "zone name %s_%s vsan %d\n" % (host, array, vsanA)
				output += "member fcalias %s\n" % host
				output += "member fcalias %s\n" % array
		return output
	elif switch == 'B':
		for host in host_hbas.keys():
			if host.endswith(switch):
				zonesetB += "member %s_%s\n" % (host, array) # Add zone to zoneset
				output += "zone name %s_%s vsan %d\n" % (host, array, vsanB)
				output += "member fcalias %s\n" % host
				output += "member fcalias %s\n" % array
		return output

if not host_hbas:
	print 'No matching Service Profiles found.'
	quit(0)
print '-' * 15
print "Creating zone config"
print '-' * 15
print "Array:", array
print '-' * 15
print "Host HBA's:"
hba_table = PrettyTable(["Host HBA", "WWPN"])
hba_table.align["Host HBA"] = "l"
hba_table.sortby = "Host HBA"
for host, hba in host_hbas.items():
    hba_table.add_row([host, hba])
print hba_table
"""
hbas_sorted = []
for host in host_hbas.keys():
	hbas_sorted.append(host)
hbas_sorted.sort()
for hba in hbas_sorted:
    print hba
"""
# create fcaliases
fcaliases_for_A = create_fcalias('A')
fcaliases_for_B = create_fcalias('B')

# create zones and zonesets
# TODO - make this work with answerfile
zones_for_A = create_zones('A')
zones_for_B = create_zones('B')

config = ''
config += '-' * 20
config += 'MDS A Config'
config += '-' * 20 #, '\n'
config += '\n\n'
config += fcaliases_for_A
config += '\n'
config += zones_for_A
config += '\n'
config += zonesetA
config += '\n'
config += 'zoneset activate name PCloud-A vsan %d' % vsanA # '\n'
config += '\n\n'
config += '-' * 20
config += 'MDS B Config'
config += '-' * 20 #, '\n'
config += '\n\n'
config += fcaliases_for_B
config += '\n'
config += zones_for_B
config += '\n'
config += zonesetB
config += '\n'
config += 'zoneset activate name PCloud-B vsan %d\n' % vsanB

mds_output = open(args.output, 'w')
mds_output.write(config)
mds_output.close
print '-' * 20
print "MDS Config successfully generated and saved to %s." % os.path.realpath(mds_output.name)

