#!/usr/bin/env python

'''
Pegasus utility for checking file integrity after transfers

Usage: pegasus-integrity-check [options]
'''
from __future__ import print_function

##
#  Copyright 2007-2017 University Of Southern California
#
#  Licensed under the Apache License, Version 2.0 (the 'License');
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing,
#  software distributed under the License is distributed on an 'AS IS' BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
##

import cmd
import errno
import glob
import json
import logging
import optparse
import os
import pprint
import re
import stat
import string
import subprocess
import sys
import tempfile
import threading
import time
import traceback

# for some reason, sometimes grp is missing, but we can do without it
try:
    import pwd
    import grp
except:
    pass

from datetime import datetime
from subprocess import STDOUT

__author__ = 'Mats Rynge <rynge@isi.edu>'



# --- classes -----------------------------------------------------------------

class Singleton(type):
    '''Implementation of the singleton pattern'''
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = \
                super(Singleton, cls).__call__(*args, **kwargs)
            cls.lock = threading.Lock()
        return cls._instances[cls]


class Tools(object):
    '''Singleton for detecting and maintaining tools we depend on
    '''
    
    __metaclass__ = Singleton
    
    _info = {}

    def find(self, executable, version_arg=None, version_regex=None, path_prepend=None):

        self.lock.acquire()
        try:
            if executable in self._info:
                if self._info[executable] is None:
                    return None
                return self._info[executable]
            
            logger.debug('Trying to detect availability/location of tool: %s'
                         %(executable))

            # initialize the global tool info for this executable
            self._info[executable] = {}
            self._info[executable]['full_path'] = None
            self._info[executable]['version'] = None
            self._info[executable]['version_major'] = None
            self._info[executable]['version_minor'] = None
            self._info[executable]['version_patch'] = None
        
            # figure out the full path to the executable
            path_entries = ['/usr/bin']
            if 'PATH' in os.environ:
                path_entries = os.environ['PATH'].split(':')
            if '' in path_entries:
                path_entries.remove('')
            if path_prepend is not None:
                for entry in path_prepend:
                    path_entries.insert(0, entry)
            
            # now walk the path
            full_path = None
            for entry in path_entries:
                full_path = entry + '/' + executable
                if os.path.isfile(full_path) and os.access(full_path, os.X_OK):
                    break
                full_path = None
            
            if full_path == None:
                logger.debug('Command \'%s\' not found in the current environment'
                            %(executable))
                self._info[executable] = None
                return self._info[executable]
            self._info[executable]['full_path'] = full_path
        
            # version
            if version_regex is None:
                version = 'N/A'
            else:
                version = backticks(executable + ' ' + version_arg + ' 2>&1')
                version = version.replace('\n', '')
                re_version = re.compile(version_regex)
                result = re_version.search(version)
                if result:
                    version = result.group(1)
                self._info[executable]['version'] = version
        
            # if possible, break up version into major, minor, patch
            re_version = re.compile('([0-9]+)\.([0-9]+)(\.([0-9]+)){0,1}')
            result = re_version.search(version)
            if result:
                self._info[executable]['version_major'] = int(result.group(1))
                self._info[executable]['version_minor'] = int(result.group(2))
                self._info[executable]['version_patch'] = result.group(4)
            if self._info[executable]['version_patch'] is None or \
               self._info[executable]['version_patch'] == '':
                self._info[executable]['version_patch'] = 0
            else:
                self._info[executable]['version_patch'] = \
                    int(self._info[executable]['version_patch'])
        
            logger.debug('Tool found: %s   Version: %s   Path: %s' 
                        % (executable, version, full_path))
            return self._info[executable]['full_path']
        finally:
            self.lock.release()


    def full_path(self, executable):
        ''' Returns the full path to a given executable '''
        self.lock.acquire()
        try:
            if executable in self._info and self._info[executable] is not None:
                return self._info[executable]['full_path']
            return None
        finally:
            self.lock.release()

    
    def major_version(self, executable):
        ''' Returns the detected major version given executable '''
        self.lock.acquire()
        try:
            if executable in self._info and self._info[executable] is not None:
                return self._info[executable]['version_major']
            return None
        finally:
            self.lock.release()
                
    
    def version_comparable(self, executable):
        ''' Returns the detected comparable version given executable '''
        self.lock.acquire()
        try:
            if executable in self._info and self._info[executable] is not None:
                return '%03d%03d%03d' %(int(self._info[executable]['version_major']), \
                                        int(self._info[executable]['version_minor']), \
                                        int(self._info[executable]['version_patch']))
            return None
        finally:
            self.lock.release()


class TimedCommand(object):
    ''' Provides a shell callout with a timeout '''
        
    def __init__(self, cmd, env_overrides = {}, timeout_secs = 6*60*60, log_cmd = True, log_outerr = True):
        self._cmd = cmd
        self._env_overrides = env_overrides.copy()
        self._timeout_secs = timeout_secs
        self._log_cmd = log_cmd
        self._log_outerr = log_outerr
        self._process = None
        self._out_file = None
        self._outerr = ''

        # used in exceptions
        self._cmd_for_exc = cmd

    def run(self):
        def target():
            
            # custom environment for the subshell
            sub_env = os.environ.copy()
            for key, value in self._env_overrides.iteritems():
                logger.debug('ENV override: %s = %s' %(key, value))
                sub_env[key] = value
            
            self._process = subprocess.Popen(self._cmd, shell=True, env=sub_env,
                                             stdout=self._out_file, stderr=STDOUT, 
                                             preexec_fn=os.setpgrp)
            self._process.communicate()

        if self._log_cmd or logger.isEnabledFor(logging.DEBUG):
            logger.info(self._cmd)
            # provide a short version in exceptions
            self._cmd_for_exc = re.sub(' .*', ' ...', self._cmd)
            
        sys.stdout.flush()
        
        # temp file for the stdout/stderr
        self._out_file = tempfile.TemporaryFile(prefix='pegasus-transfer-', suffix='.out')
        
        thread = threading.Thread(target=target)
        thread.start()

        thread.join(self._timeout_secs)
        if thread.isAlive():
            # do our best to kill the whole process group
            try:
                # os.killpg did not work in all environments
                #os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                kill_cmd = 'kill -TERM -%d' %(os.getpgid(self._process.pid))
                kp = subprocess.Popen(kill_cmd, shell=True)
                kp.communicate()
                self._process.terminate()
            except:
                pass
            thread.join()
            # log the output
            self._out_file.seek(0)
            stdout = str.strip(self._out_file.read())
            if len(stdout) > 0:
                logger.info(stdout)
            self._out_file.close()
            raise RuntimeError('Command timed out after %d seconds: %s' %(self._timeout_secs, self._cmd_for_exc))
        
        # log the output
        self._out_file.seek(0)
        self._outerr = str.strip(self._out_file.read())
        if self._log_outerr and len(self._outerr) > 0:
            logger.info(self._outerr)
        self._out_file.close()
        
        if self._process.returncode != 0:
            raise RuntimeError('Command exited with non-zero exit code (%d): %s' \
                               %(self._process.returncode, self._cmd_for_exc))


    def get_outerr(self):
        '''
        returns the combined stdout and stderr from the command
        '''
        return self._outerr
    
    
    def get_exit_code(self):
        '''
        returns the exit code from the process
        '''
        return self._process.returncode

    

# --- global variables ----------------------------------------------------------------

prog_dir  = os.path.realpath(os.path.join(os.path.dirname(sys.argv[0])))
prog_base = os.path.split(sys.argv[0])[1]   # Name of this program

logger = logging.getLogger('my_logger')

count_succeeded = 0
count_failed = 0
total_timing = 0.0

# --- functions ----------------------------------------------------------------


def setup_logger(debug_flag):
    
    # log to the console
    console = logging.StreamHandler()
    
    # default log level - make logger/console match
    logger.setLevel(logging.INFO)
    console.setLevel(logging.INFO)

    # debug - from command line
    if debug_flag:
        logger.setLevel(logging.DEBUG)
        console.setLevel(logging.DEBUG)

    # formatter
    formatter = logging.Formatter('Integrity check: %(message)s')
    console.setFormatter(formatter)
    logger.addHandler(console)
    logger.debug('Logger has been configured')


def backticks(cmd_line):
    '''
    what would a python program be without some perl love?
    '''
    return subprocess.Popen(cmd_line, shell=True,
                            stdout=subprocess.PIPE).communicate()[0]


def json_object_decoder(obj):
    '''
    utility function used by json.load() to parse some known objects into equivalent Python objects
    '''
    if 'type' in obj and obj['type'] == 'transfer':
        t = Transfer()
        # src
        for surl in obj['src_urls']:
            priority = None
            if 'priority' in surl:
                priority = int(surl['priority']) 
            t.add_src(surl['site_label'], surl['url'], priority)
        for durl in obj['dest_urls']:
            priority = None
            if 'priority' in durl:
                priority = int(durl['priority']) 
            t.add_dst(durl['site_label'], durl['url'], priority)
        return t
    elif 'type' in obj and obj['type'] == 'mkdir':
        m = Mkdir()
        m.set_url(obj['target']['site_label'], obj['target']['url'])
        return m
    elif 'type' in obj and obj['type'] == 'remove':
        r = Remove()
        r.set_url(obj['target']['site_label'], obj['target']['url'])
        if 'recursive' in obj['target']:
            r.set_recursive(obj['target']['recursive'])
        return r
    return obj


def read_meta_data(f):
    '''
    Reads transfers from the new JSON based input format
    '''
    data = []
    try:
        fp = open(f, 'r')
        data = json.load(fp)
        fp.close()
    except Exception as err:
        logger.critical('Error parsing the meta data: ' + str(err))
    return data


def myexit(rc):
    '''
    system exit without a stack trace
    '''
    try:
        sys.exit(rc)
    except SystemExit:
        sys.exit(rc)


def generate_sha256(fname):
    '''
    Generates a sha256 hash for the given file
    '''

    tools = Tools()
    tools.find('openssl', 'version', '([0-9]+\.[0-9]+\.[0-9]+)')
    tools.find('sha256sum', '--version', '([0-9]+\.[0-9]+)')
  
    if tools.full_path('openssl'):
        cmd = tools.full_path('openssl')
        if tools.version_comparable('openssl') < '001001000':
            cmd += ' sha -sha256'
        else:
            cmd += ' sha256'
        cmd += ' ' + fname
    elif tools.full_path('sha256sum'):
        cmd = tools.full_path('sha256sum')
        cmd += ' ' + fname + ' | sed \'s/ .*//\''
    else:
        logger.error('openssl or sha256sum not found!')
        return None
    
    if not os.path.exists(fname):
        logger.error('File ' + fname + ' does not exist')
        return None

    # generate the checksum
    tc = TimedCommand(cmd, log_cmd=False, log_outerr=False)
    tc.run()
    if tc.get_exit_code() != 0:
        logger.error('Unable to determine sha256: ' + tc.get_outerr())
        return None

    sha256 = tc.get_outerr()
    sha256 = sha256.strip()
    sha256 = sha256[-64:]
    if len(sha256) != 64:
        logger.warn('Unable to determine sha256 of ' + fname)
  
    return sha256


def iso8601(ts):
    '''
    Formats a UNIX timestamp in ISO 8601 format
    '''
    dt = datetime.utcfromtimestamp(ts)
    return dt.isoformat()


def generate_yaml(lfn, pfn):
    '''
    Generates kickstart yaml for the given file
    '''
    
    ts_start = time.time()
    sha256 = generate_sha256(pfn)
    if sha256 == None:
        return None
    ts_end = time.time()

    return '      sha256: %s\n      checksum_timing: %.3f\n' %(sha256, ts_end - ts_start)


def generate_fullstat_yaml(lfn, pfn):
    '''
    Generates kickstart yaml for the given file
    '''
    
    ts_start = time.time()
    sha256 = generate_sha256(pfn)
    if sha256 == None:
        return None
    ts_end = time.time()

    yaml = ''
    yaml += '    "%s":\n' %(lfn)
    yaml += '      comment: entry generated by pegasus-integrity\n'
    yaml += '      file_name: "%s"\n' %(pfn)

    try:
        s = os.stat(pfn)
    except:
        # if we can't stat, just return
        return ''

    uname = ''
    try:
        uname = pwd.getpwuid(s.st_uid).pw_name
    except:
        pass
    gname = ''
    try:
        gname = grp.getgrgid(s.st_gid).gr_name
    except:
        pass
    yaml += ('      mode: 0o%o\n'
             '      size: %d\n'
             '      inode: %d\n'
             '      nlink: %d\n' 
             '      mtime: %s\n'
             '      atime: %s\n'
             '      ctime: %s\n'
             '      uid: %d\n'
             '      user: %s\n'
             '      gid: %d\n'
             '      group: %s\n'
             '      output: True\n'
             %(s.st_mode, s.st_size, s.st_ino, s.st_nlink,
               iso8601(s.st_mtime), iso8601(s.st_atime), iso8601(s.st_ctime),
               s.st_uid, uname, s.st_gid, gname))
    yaml += ('      sha256: %s\n'
             '      checksum_timing: %.3f\n' %(sha256, ts_end - ts_start))
    return yaml


def check_integrity(fname, lfn, meta_data):
    '''
    Checks the integrity of a file given a set of metadata
    '''
    
    global count_succeeded
    global count_failed
    global total_timing

    ts_start = time.time()

    if lfn is None or lfn == '':
        lfn = fname
    
    # find the expected checksum in the metadata
    expected_sha256 = None
    for entry in meta_data:
        if entry['_id'] == lfn:
            if '_attributes' in entry and 'checksum.value' in entry['_attributes']:
                expected_sha256 = entry['_attributes']['checksum.value']
    if expected_sha256 is None:
        logger.error('No checksum in the meta data for ' + lfn)
        return False

    current_sha256 = generate_sha256(fname)
    
    ts_end = time.time()

    total_timing += ts_end - ts_start
    
    # now compare them
    if current_sha256 != expected_sha256:
        logger.error('%s: Expected checksum (%s) does not match the calculated checksum (%s) (timing: %.3f)' \
                     %(fname, expected_sha256, current_sha256, ts_end - ts_start))
        count_failed += 1
        return False

    count_succeeded += 1
    return True


def dump_timing_json():
    '''
    outputs a timing block for Pegasus monitoring
    '''
    data = {
        'ts': int(time.time()), 
        'monitoring_event': 'int.metric', 
        'payload': [ {
                'event': 'check',
                'file_type': 'input',
                'succeeded': count_succeeded,
                'failed': count_failed,
                'duration': '%.3f' % total_timing
            }
        ]
    }
    print('@@@MONITORING_PAYLOAD - START@@@' +json.dumps(data) + '@@@MONITORING_PAYLOAD - END@@@')

# --- main ----------------------------------------------------------------------------

def main():
    global threads
    global stats_start
    global stats_end
    global symlink_file_transfer
    
    # dup stderr onto stdout
    sys.stderr = sys.stdout
    
    # Configure command line option parser
    prog_usage = 'usage: %s [options]' % (prog_base)
    parser = optparse.OptionParser(usage=prog_usage)
    
    parser.add_option('', '--generate', action = 'store', dest = 'generate_files',
                      help = 'Generate a SHA256 hash for a set of files')
    parser.add_option('', '--generate-yaml', action = 'store', dest = 'generate_yaml',
                      help = 'Generate hashes for the given file, output to kickstart yaml.')
    parser.add_option('', '--generate-fullstat-yaml', action = 'store', dest = 'generate_fullstat_yaml',
                      help = 'Generate hashes for the given file, output to kickstart yaml.')
    parser.add_option('', '--generate-xmls', action = 'store', dest = 'generate_xmls',
                      help = 'Generate hashes for the given file, output to kickstart xml.')
    parser.add_option('', '--generate-fullstat-xmls', action = 'store', dest = 'generate_fullstat_xmls',
                      help = 'Generate hashes for the given file, output to kickstart xml.')
    parser.add_option('', '--verify', action = 'store', dest = 'verify_files',
                      help = 'Verify the hash for the given file.')
    parser.add_option('', '--print-timings', action = 'store_true', dest = 'print_timings',
                      help = 'Display timing data after verifying files')
    parser.add_option('', '--debug', action = 'store_true', dest = 'debug',
                      help = 'Enables debugging output.')
    
    # Parse command line options
    (options, args) = parser.parse_args()
    setup_logger(options.debug)

    # sanity checks
    if sum([options.generate_files != None,
            options.generate_yaml != None,
            options.generate_fullstat_yaml != None,
            options.generate_xmls != None,
            options.generate_fullstat_xmls != None,
            options.verify_files != None]) != 1:
        logger.error('One, and only one, of --generate-* and --verify needs to be specified')
        parser.print_help()
        sys.exit(1)
    
    if options.generate_files:
        for f in str.split(options.generate_files, ':'):
            results = generate_sha256(f)
            if not results:
                myexit(1)
            print(results + '  ' + f)

    elif options.generate_yaml:
        for f in str.split(options.generate_yaml, ':'):
            # lfn can be encoded in the file name in the format lfn=pfn
            lfn = None
            pfn = f
            if '=' in f:
                (lfn, pfn) = str.split(f, '=', 1)
            results = generate_yaml(lfn, pfn)
            if not results:
                myexit(1)
            print(results)
    
    elif options.generate_fullstat_yaml:
        for f in str.split(options.generate_fullstat_yaml, ':'):
            # lfn can be encoded in the file name in the format lfn=pfn
            lfn = None
            pfn = f
            if '=' in f:
                (lfn, pfn) = str.split(f, '=', 1)
            results = generate_fullstat_yaml(lfn, pfn)
            if not results:
                myexit(1)
            #if lfn is not None and 'KICKSTART_INTEGRITY_DATA' in os.environ:
            if 'KICKSTART_INTEGRITY_DATA' in os.environ:
                f = open(os.environ['KICKSTART_INTEGRITY_DATA'], 'a')
                f.write(results)
                f.close()
            else:
                print(results)

    elif options.verify_files:
        # read all the .meta files in the current working dir
        meta_data = []
        for meta_file in glob.glob('*.meta'):
            logger.debug('Loading metadata from %s' % (meta_file))
            all_md = read_meta_data(meta_file)
            for entry in all_md:
                meta_data.append(entry)
    
        if options.debug: 
            pprint.PrettyPrinter(indent=4).pprint(meta_data)

        # the files can be provided directly, or via stdin
        files = ''
        if options.verify_files == 'stdin':
            files = sys.stdin.read().strip()
        else:
            files = options.verify_files

        # now check the files    
        for f in str.split(files, ':'):
            # lfn can be encoded in the file name in the format lfn=pfn
            lfn = None
            pfn = f
            if '=' in f:
                (lfn, pfn) = str.split(f, '=', 1)
            results = check_integrity(pfn, lfn, meta_data)
            if not results:
                if options.print_timings:
                    dump_timing_json()
                myexit(1)
        if options.print_timings:
            dump_timing_json()
        
    myexit(0)


if __name__ == '__main__':
    main()
    
