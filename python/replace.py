#!/usr/bin/python
#----------------------------------------------------------------------------------------------
# Copyright 2012-2015 VMware, Inc. All rights reserved
# This file is open source software released under the terms of the BSD 3-Clause license,
# http://opensource.org/licenses/BSD-3-Clause
# NAME: Python based find-replace command line utility
# DESCRIPTION: Command line utility to do find-replace accross possibly multiple files.  If you find using sed frustrating because of the necessity to escape strings all the time this utility may be for you
# AUTHOR: Aaron Spear aspear@vmware.com
#----------------------------------------------------------------------------------------------

from optparse import Option
from optparse import OptionParser
import sys
import re
import os
import traceback
import glob

EXECUTABLE = 'replace.py'
VERSION_NUMBER = '0.3'

DESCRIPTION = ('Perform a find and replace operation for any number of name=value pairs on file(s)\n' +
			'specified by the file glob patterns. Pairs are plain text by default, but\n' +
			'can optionally be regular expressions as well.  Embedded = chars should be escaped\n' +
			'using backslash, e.g. \\=.\n' +
			'EXAMPLES:\n' +
			'        replace name1=value1 name2=value2 nameN=valueN  ./path/to/file1.xml ./path/to/fileN.xml\n' +
			'        replace VERSION=1.2.3 RELEASE=mn.next MILESTONE=beta ../publish/vcdp/*.xml\n')

#all output goes through this one function in an effort to deal with python version differences
#in stdout support and perhaps also allow some graceful redirection
def stdout( lineString ):
	sys.stdout.write(lineString)
	sys.stdout.write("\n")

def stderr( lineString ):
	sys.stderr.write(lineString)
	sys.stderr.write("\n")

def findSplitIndex(line):
	index=0
	while index != -1:
		index = line.find("=",index)
		if index > 0:
			c = line[index-1]
			if c != '\\':
				return index
		# not found search from next char
		index = index + 1
	return -1


def readRepFilePairs(repFilePath, nameValuePairMap):
    inputFile  = open(repFilePath,"r")
    if inputFile == False:
	   stderr("ERROR: unable to open input file "+repFilePath)
	   sys.exit(2)
    for line in inputFile.readlines():
        if line.startswith('#'):
            continue;
        line = line.strip()
        # find the first instance of '=' that is not escaped and split on that index.
        index = findSplitIndex(line)
        if index > -1:
		    name = line[:index]
		    value = line[index+1:]
		    # it is possible that there are escaped = chars. replace those with single equals chars
		    name = name.replace("\=","=")
		    value = value.replace("\=","=")
		    nameValuePairMap[name] = value
    inputFile.close()

def _setFilePermissions( path, mode, uid, gid ):
	try:
		os.chown(path,uid,gid)
	except Exception as e:
		stderr("ERROR: while trying to change owner on '%s': %s\n" % (path, str(e)))
	try:
		os.chmod(path,mode)
	except Exception as e:
		stderr("ERROR: while trying to change mode '%s': %s\n" % (path, str(e)))

#----------------------------------------------------------------------------------------------
# overload that takes a map of name=value pairs, a file path/name list, and a verbose boolean flag
def replace( nameValuePairMap, filePathList, verbose, dryrun,noprintunchanged=False,useregexsub=False):

	if dryrun == True and verbose:
		stdout("Performing dry run")

	if verbose == True:
		for name,value in nameValuePairMap.items():
			stdout('NAME='+name+' VALUE='+value)

	totalFilesReplaced = 0

	if len(filePathList) == 0:
		stdout("NO FILES MATCHED SPECIFIED PATTERNS")
		sys.exit(1)

	for inputFileName in filePathList:
		changesInFile = 0

		if not noprintunchanged:    # yeah , sorry about the double negative
			stdout(inputFileName)
			emittedFileName = True
		else:
			emittedFileName = False

		try:
			outputFileName = inputFileName + ".temp";
			inputFile  = open(inputFileName,"r")
			if inputFile == False:
				stderr("ERROR: unable to open input file "+inputFileName)
				continue
			statstruct = os.stat(inputFileName)

			if dryrun == False:
				outputFile = open(outputFileName, "w")
			linenumber = 1
			for line in inputFile.readlines():
				newLine = line
				for key, value in nameValuePairMap.items():
					if useregexsub:
						newLine = re.sub(key, value, newLine)
					else:
						newLine = newLine.replace(key,value)
				if dryrun == False:
					outputFile.write(newLine)

				if newLine != line:
					changesInFile = changesInFile + 1
					if not emittedFileName:
						stdout(inputFileName)
						emittedFileName = True
					if (dryrun == True) or (verbose == True):
						stdout("    " + str(linenumber)+": '"+ newLine.rstrip("\n") + "'")
				linenumber = linenumber + 1


			if dryrun == False:
				if changesInFile != 0:
					stdout("    "  + str(changesInFile)+" lines changed")
			else:
				if verbose:
					stdout("    "  + str(changesInFile)+" lines WOULD BE changed")
			if changesInFile != 0:
				totalFilesReplaced = totalFilesReplaced + 1

			inputFile.close();

			if dryrun == False:
				outputFile.close();
				os.remove(inputFileName)
				# TODO add code for permissions
				os.rename(outputFileName,inputFileName)
				_setFilePermissions( inputFileName, statstruct.st_mode, statstruct.st_uid, statstruct.st_gid )

		except Exception, inst:
			inputFile.close()
			if dryrun == False:
				outputFile.close()
			stderr("Exception while handling files")
			#, type(inst)     # the exception instance
			#print inst.args      # arguments stored in .args
			traceback.print_exc()
			sys.exit(1)

	if verbose or totalFilesReplaced != 0:
		if dryrun == False:
			stdout(str(totalFilesReplaced)+ " files changed.")
		else:
			stdout(str(totalFilesReplaced)+ " files WOULD BE changed.")

# this overload is used so that we can do multiple instances of command line
# arguments
class MultipleOption(Option):
    ACTIONS = Option.ACTIONS + ("extend",)
    STORE_ACTIONS = Option.STORE_ACTIONS + ("extend",)
    TYPED_ACTIONS = Option.TYPED_ACTIONS + ("extend",)
    ALWAYS_TYPED_ACTIONS = Option.ALWAYS_TYPED_ACTIONS + ("extend",)

    def take_action(self, action, dest, opt, value, values, parser):
        if action == "extend":
            values.ensure_value(dest, []).append(value)
        else:
            Option.take_action(self, action, dest, opt, value, values, parser)

#----------------------------------------------------------------------------------------------
# overload that takes a string command line according to that shown in usage above
def main(argv):
	verbose = False
	dryrun = False
	repFilePath = None
	noprintunchanged = False
	useregex = False

	# parse the command-line options and arguments
	optparser = OptionParser(option_class=MultipleOption,
	        usage='usage: %prog [options] <name=value pair(s)> <file glob(s)>',
	        description=DESCRIPTION,
	        add_help_option=False,
	        prog=EXECUTABLE,
	        version=VERSION_NUMBER)

	optparser.add_option('-h', '--help',
	        action='store_true', dest='help',
	        help='Display this information')

	optparser.add_option('-v', '--verbose',
	        action='store_true', dest='verbose',
	        help=' Verbose display of results')

	optparser.add_option('-d', '--dryrun',
	        action='store_true', dest='dryrun',
	        help="Perform a dry run only, reporting what the tool would do without making any changes.")

	optparser.add_option('--noprintunchanged',
	        action='store_true', dest='noprintunchanged',
	        help="If provided, do not print messages for files that are not changed.")

	optparser.add_option('--useregex',
	        action='store_true', dest='useregex',
	        help="If provided, the find/replace values are regular expressions.  Default is plain text.")

	optparser.add_option('--repfile',
	        action='store', dest='repfile',
	        help='File of replacements to use.  name=value on each line.  Leading # is a comment.')

	options, args = optparser.parse_args()

	if options.help or len(args) == 0:
	    optparser.print_help()
	    sys.exit(0)

	if options.verbose and options.verbose == True:
	    verbose = True
	if options.dryrun and options.dryrun == True:
	    dryrun = True
	if options.noprintunchanged and options.noprintunchanged == True:
	    noprintunchanged = True
	if options.useregex and options.useregex == True:
	    useregex = True
	if options.repfile:
		repFilePath = options.repfile

	nameValuePairMap = {}
	filePathList = []

	if repFilePath != None:
		readRepFilePairs(repFilePath, nameValuePairMap)

	# split args into a map of name=value pairs and other args into a file list
	# for processing
	for arg in args:
		if (arg.find("=") > 0):
			name,value = arg.split("=");
			nameValuePairMap[name] = value
		else:
			globMatchingFiles = glob.glob(arg)
			filePathList = filePathList + globMatchingFiles

	if verbose == True:
		for name,value in nameValuePairMap.items():
			stdout('\tNAME='+name+' VALUE='+value)

	#call the other overload
	replace( nameValuePairMap,filePathList,verbose,dryrun,noprintunchanged,useregex)

if __name__ == "__main__":
	main(sys.argv[1:])
