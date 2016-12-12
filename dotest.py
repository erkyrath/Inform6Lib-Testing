#!/usr/bin/env python3

# DoTest: a really simple IF regression tester.
#   Andrew Plotkin <erkyrath@eblong.com>
#   This script is in the public domain.
#
# This is derived from regtest.py, although it's not identical. This
# version requires Python 3 (not compatible with Py2) and is adapted
# to compile I6 code before running tests.
#
# For the original, see <http://eblong.com/zarf/plotex/regtest.html>

import sys
import os
import optparse
import select
import fnmatch
import subprocess
import re
import types
import math
import time

terppath = None
terpargs = []
precommands = []

totalerrors = 0

popt = optparse.OptionParser()

popt.add_option('-c', '--compiler',
                action='store', dest='compilerpath',
                default='inform',
                help='Inform 6 compiler')
popt.add_option('-G', '--glulx',
                action='store_true', dest='glulxmode',
                help='Compile to Glulx (default)')
popt.add_option('-Z', '--zcode',
                action='store_true', dest='zcodemode',
                help='Compile to Z-code')
popt.add_option('--library', '--lib',
                action='store', dest='librarypath',
                default='inform6lib',
                help='Inform 6 library directory')
popt.add_option('-i', '--interpreter', '--terp',
                action='store', dest='terppath',
                help='interpreter to execute')
popt.add_option('-l', '--list',
                action='store_true', dest='listonly',
                help='list all tests (or all matching tests)')
popt.add_option('-p', '--pre', '--precommand',
                action='append', dest='precommands',
                help='extra command to execute before (each) test')

def timeout_option_cb(option, opt_str, value, parser):
    if value < 0.0 or math.isnan(value):
        raise optparse.OptionValueError('Timeout must be non-negative.')
    setattr(parser.values, option.dest, value)

popt.add_option('-t', '--timeout',
                action='callback', callback=timeout_option_cb,
                dest='timeout_secs', type='float', default=1.0,
                help='timeout interval (default: 1.0 secs)')
popt.add_option('--vital',
                action='store_true', dest='vital',
                help='abort a test on the first error')
popt.add_option('-v', '--verbose',
                action='store_true', dest='verbose',
                help='display the transcripts as they run')

(opts, args) = popt.parse_args()

if (not args):
    print('usage: dotest.py [options] TESTFILES...')
    sys.exit(1)

class RegTest:
    """RegTest represents one test in the test file. (That is, a block
    beginning with a single asterisk.)

    A test is one session of the game, from the beginning. (Not necessarily
    to the end.) After every game command, tests can be run.
    """
    def __init__(self, name):
        self.name = name
        self.gamefile = None   # use global gamefile
        self.terp = None       # global terppath, terpargs
        self.precmd = None
        self.cmds = []
    def __repr__(self):
        return '<RegTest %s>' % (self.name,)
    def addcmd(self, cmd):
        self.cmds.append(cmd)

class Command:
    """Command is one cycle of a RegTest -- a game input, followed by
    tests to run on the game's output.
    """
    def __init__(self, cmd, type='line'):
        self.type = type
        if self.type == 'line':
            self.cmd = cmd
        elif self.type == 'char':
            self.cmd = None
            if len(cmd) == 0:
                self.cmd = '\n'
            elif len(cmd) == 1:
                self.cmd = cmd
            elif cmd.lower().startswith('0x'):
                self.cmd = unichr(int(cmd[2:], 16))
            else:
                try:
                    self.cmd = unichr(int(cmd))
                except:
                    pass
            if self.cmd is None:
                raise Exception('Unable to interpret char "%s"' % (cmd,))
        elif self.type == 'timer':
            self.cmd = None
        elif self.type == 'include':
            self.cmd = cmd
        elif self.type == 'fileref_prompt':
            self.cmd = cmd
        else:
            raise Exception('Unknown command type: %s' % (type,))
        self.checks = []
    def __repr__(self):
        return '<Command "%s">' % (self.cmd,)
    def addcheck(self, ln):
        args = {}
        # First peel off "!" and "{...}" prefixes
        while True:
            match = re.match('!|{[a-z]*}', ln)
            if not match:
                break
            ln = ln[match.end() : ].strip()
            val = match.group()
            if val == '!' or val == '{invert}':
                args['inverse'] = True
            elif val == '{status}':
                args['instatus'] = True
            elif val == '{vital}':
                args['vital'] = True
            else:
                raise Exception('Unknown test modifier: %s' % (val,))
        # Then the test itself, which may have many formats. We try
        # each of the classes in the checkclasses array until one
        # returns a Check.
        for cla in checkclasses:
            check = cla.buildcheck(ln, args)
            if check is not None:
                self.checks.append(check)
                break
        else:
            raise Exception('Unrecognized test: %s' % (ln,))

class Check:
    """Represents a single test (applied to the output of a game command).

    This can be applied to the story window or the status window. (The
    model is simplistic and assumes there is exactly one story window
    and at most one status window.)

    An "inverse" test has reversed sense.

    A "vital" test will end the test run on failure.
    
    This is a virtual base class. Subclasses should customize the subeval()
    method to examine a list of lines, and return None (on success) or a
    string (explaining the failure).
    """
    inrawdata = False
    inverse = False
    instatus = False

    @classmethod
    def buildcheck(cla, ln, args):
        raise Exception('No buildcheck method defined for class: %s' % (cla.__name__,))
    
    def __init__(self, ln, **args):
        self.inverse = args.get('inverse', False)
        self.instatus = args.get('instatus', False)
        self.vital = args.get('vital', False) or opts.vital
        self.ln = ln
        
    def __repr__(self):
        val = self.ln
        if len(val) > 32:
            val = val[:32] + '...'
        invflag = '!' if self.inverse else ''
        if self.instatus:
            invflag += '{status}'
        detail = self.reprdetail()
        return '<%s %s%s"%s">' % (self.__class__.__name__, detail, invflag, val,)

    def reprdetail(self):
        return ''

    def eval(self, state):
        if not self.inrawdata:
            if self.instatus:
                lines = state.statuswin
            else:
                lines = state.storywin
        else:
            if self.instatus:
                lines = state.statuswindat
            else:
                lines = state.storywindat
        res = self.subeval(lines)
        if (not self.inverse):
            return res
        else:
            if res:
                return
            return 'inverse test should fail'
    def subeval(self, lines):
        return 'not implemented'

class RegExpCheck(Check):
    """A Check which looks for a regular expression match in the output.
    """
    @classmethod
    def buildcheck(cla, ln, args):
        # Matches check lines starting with a slash
        if (ln.startswith('/')):
            return RegExpCheck(ln[1:].strip(), **args)
    def subeval(self, lines):
        for ln in lines:
            if re.search(self.ln, ln):
                return
        return 'not found'
        
class LiteralCheck(Check):
    """A Check which looks for a literal string match in the output.
    """
    @classmethod
    def buildcheck(cla, ln, args):
        # Always matches
        return LiteralCheck(ln, **args)
    def subeval(self, lines):
        for ln in lines:
            if self.ln in ln:
                return
        return 'not found'

class LiteralCountCheck(Check):
    """A Check which looks for a literal string match in the output,
    which must occur at least N times.
    """
    @classmethod
    def buildcheck(cla, ln, args):
        match = re.match('{count=([0-9]+)}', ln)
        if match:
            ln = ln[ match.end() : ].strip()
            res = LiteralCountCheck(ln, **args)
            res.count = int(match.group(1))
            return res
    def reprdetail(self):
        return '{count=%d} ' % (self.count,)
    def subeval(self, lines):
        counter = 0
        for ln in lines:
            start = 0
            while True:
                pos = ln.find(self.ln, start)
                if pos < 0:
                    break
                counter += 1
                start = pos+1
                if counter >= self.count:
                    return
        if counter == 0:
            return 'not found'
        else:
            return 'only found %d times' % (counter,)

# This script only supports three kinds of checks.
checkclasses = [ RegExpCheck, LiteralCountCheck, LiteralCheck ]

class GameState:
    """The GameState class wraps the connection to the interpreter subprocess
    (the pipe in and out streams). It's responsible for sending commands
    to the interpreter, and receiving the game output back.

    Currently this class is set up to manage exactly one story window
    and exactly one status window. (A missing window is treated as blank.)
    This is not very general -- we should understand the notion of multiple
    windows -- but it's adequate for now.

    This is a virtual base class. Subclasses should customize the
    initialize, perform_input, and accept_output methods.
    """
    def __init__(self, infile, outfile):
        self.infile = infile
        self.outfile = outfile
        # Lists of strings
        self.statuswin = []
        self.storywin = []
        # Lists of line data lists
        self.statuswindat = []
        self.storywindat = []

    def initialize(self):
        pass

    def perform_input(self, cmd):
        raise Exception('perform_input not implemented')
        
    def accept_output(self):
        raise Exception('accept_output not implemented')
    
class GameStateRemGlk(GameState):
    """Wrapper for a RemGlk-based interpreter. This can in theory handle
    any I/O supported by Glk. But the current implementation is limited
    to line and char input, and no more than one status (grid) window.
    Multiple story (buffer) windows are accepted, but their output for
    a given turn is agglomerated.
    """

    @staticmethod
    def extract_text(line):
        # Extract the text from a line object, ignoring styles.
        con = line.get('content')
        if not con:
            return ''
        dat = [ val.get('text') for val in con ]
        return ''.join(dat)
    
    @staticmethod
    def extract_raw(line):
        # Extract the content array from a line object.
        con = line.get('content')
        if not con:
            return []
        return con
    
    def initialize(self):
        import json
        update = { 'type':'init', 'gen':0,
                   'metrics': { 'width':80, 'height':40 },
                   'support': [ 'timer' ],
                   }
        cmd = json.dumps(update)
        self.infile.write((cmd+'\n').encode())
        self.infile.flush()
        self.generation = 0
        self.windows = {}
        # This doesn't track multiple-window input the way it should,
        # nor distinguish hyperlink input state across multiple windows.
        self.lineinputwin = None
        self.charinputwin = None
        self.specialinput = None
        self.hyperlinkinputwin = None
        
    def perform_input(self, cmd):
        import json
        if cmd.type == 'line':
            if not self.lineinputwin:
                raise Exception('Game is not expecting line input')
            update = { 'type':'line', 'gen':self.generation,
                       'window':self.lineinputwin, 'value':cmd.cmd
                       }
        elif cmd.type == 'char':
            if not self.charinputwin:
                raise Exception('Game is not expecting char input')
            val = cmd.cmd
            if val == '\n':
                val = 'return'
            # We should handle arrow keys, too
            update = { 'type':'char', 'gen':self.generation,
                       'window':self.charinputwin, 'value':val
                       }
        elif cmd.type == 'timer':
            update = { 'type':'timer', 'gen':self.generation }
        elif cmd.type == 'fileref_prompt':
            if self.specialinput != 'fileref_prompt':
                raise Exception('Game is not expecting a fileref_prompt')
            update = { 'type':'specialresponse', 'gen':self.generation,
                       'response':'fileref_prompt', 'value':cmd.cmd
                       }
        else:
            raise Exception('Rem mode does not recognize command type: %s' % (cmd.type))
        cmd = json.dumps(update)
        self.infile.write((cmd+'\n').encode())
        self.infile.flush()
        
    def accept_output(self):
        import json
        output = bytearray()
        update = None

        timeout_time = time.time() + opts.timeout_secs
        timeout_secs = opts.timeout_secs

        # Read until a complete JSON object comes through the pipe or we time
        # out. We sneakily rely on the fact that RemGlk always uses dicts as
        # the JSON object, so it always ends with "}".
        while (select.select([self.outfile],[],[], timeout_secs)[0] != []):
            ch = self.outfile.read(1)
            if ch == b'':
                # End of stream. Hopefully we have a valid object.
                dat = output.decode()
                update = json.loads(dat)
                break
            output += ch
            if (output[-1] == ord('}')):
                # Test and see if we have a valid object.
                dat = output.decode()
                try:
                    update = json.loads(dat)
                    break
                except:
                    pass
            timeout_secs = timeout_time - time.time()
            if timeout_secs <= 0.0:
                break

        if not update:
            raise Exception('Timed out')

        # Parse the update object. This is complicated. For the format,
        # see http://eblong.com/zarf/glk/glkote/docs.html

        self.generation = update.get('gen')

        windows = update.get('windows')
        if windows is not None:
            self.windows = {}
            for win in windows:
                id = win.get('id')
                self.windows[id] = win
            grids = [ win for win in self.windows.values() if win.get('type') == 'grid' ]
            if len(grids) > 1:
                raise Exception('Cannot handle more than one grid window')
            if not grids:
                self.statuswin = []
                self.statuswindat = []
            else:
                win = grids[0]
                height = win.get('gridheight', 0)
                if height < len(self.statuswin):
                    self.statuswin = self.statuswin[0:height]
                    self.statuswindat = self.statuswindat[0:height]
                while height > len(self.statuswin):
                    self.statuswin.append('')
                    self.statuswindat.append([])

        contents = update.get('content')
        if contents is not None:
            for content in contents:
                id = content.get('id')
                win = self.windows.get(id)
                if not win:
                    raise Exception('No such window')
                if win.get('type') == 'buffer':
                    self.storywin = []
                    self.storywindat = []
                    text = content.get('text')
                    if text:
                        for line in text:
                            dat = self.extract_text(line)
                            if (opts.verbose):
                                if (dat != '>'):
                                    print(dat)
                            if line.get('append') and len(self.storywin):
                                self.storywin[-1] += dat
                            else:
                                self.storywin.append(dat)
                            dat = self.extract_raw(line)
                            if line.get('append') and len(self.storywindat):
                                self.storywindat[-1].append(dat)
                            else:
                                self.storywindat.append([dat])
                elif win.get('type') == 'grid':
                    lines = content.get('lines')
                    for line in lines:
                        linenum = line.get('line')
                        dat = self.extract_text(line)
                        if linenum >= 0 and linenum < len(self.statuswin):
                            self.statuswin[linenum] = dat
                        dat = self.extract_raw(line)
                        if linenum >= 0 and linenum < len(self.statuswindat):
                            self.statuswindat[linenum].append(dat)

        inputs = update.get('input')
        specialinputs = update.get('specialinput')
        if specialinputs is not None:
            self.specialinput = specialinputs.get('type')
            self.lineinputwin = None
            self.charinputwin = None
            self.hyperlinkinputwin = None
        elif inputs is not None:
            self.specialinput = None
            self.lineinputwin = None
            self.charinputwin = None
            self.hyperlinkinputwin = None
            for input in inputs:
                if input.get('type') == 'line':
                    if self.lineinputwin:
                        raise Exception('Multiple windows accepting line input')
                    self.lineinputwin = input.get('id')
                if input.get('type') == 'char':
                    if self.charinputwin:
                        raise Exception('Multiple windows accepting char input')
                    self.charinputwin = input.get('id')
                if input.get('hyperlink'):
                    self.hyperlinkinputwin = input.get('id')


# Parse a test file (an Inform 6 source file with test data stuck on the
# end). Return a list of RegTests.
def parse_testfile(filename):
    re_endsource = re.compile('^\\s*#end\\s*;\\s*[!]\\s*test', re.IGNORECASE)
    
    fl = open(filename)

    # First skip the Inform source code.
    while True:
        ln = fl.readline()
        if not ln:
            raise Exception('Source file has no #end!test line')
        if re_endsource.match(ln):
            break

    # Now create the list of tests.

    testls = []
    testmap = {}

    curtest = None
    curcmd = None

    while True:
        ln = fl.readline()
        if (not ln):
            break
        ln = ln.strip()
        if (not ln or ln.startswith('#')):
            continue

        if (ln.startswith('**')):
            ln = ln[2:].strip()
            pos = ln.find(':')
            if (pos < 0):
                continue
            key = ln[:pos].strip()
            val = ln[pos+1:].strip()
            if not curtest:
                raise Exception('Unknown option: ** ' + key)
            else:
                if (key == 'game'):
                    curtest.gamefile = val
                elif (key == 'interpreter'):
                    subls = val.split()
                    curtest.terp = (subls[0], subls[1:])
                else:
                    raise Exception('Unknown option: ** ' + key + ' in * ' + curtest.name)
            continue
        
        if (ln.startswith('*')):
            ln = ln[1:].strip()
            if (ln in testmap):
                raise Exception('Test name used twice: ' + ln)
            curtest = RegTest(ln)
            testls.append(curtest)
            testmap[curtest.name] = curtest
            curcmd = Command('(init)')
            curtest.precmd = curcmd
            continue

        if (ln.startswith('>')):
            # Peel off the "{...}" prefix, if found.
            match = re.match('>{([a-z_]*)}', ln)
            if not match:
                cmdtype = 'line'
                ln = ln[1:].strip()
            else:
                cmdtype = match.group(1)
                ln = ln[match.end() : ].strip()
            curcmd = Command(ln, type=cmdtype)
            curtest.addcmd(curcmd)
            continue

        curcmd.addcheck(ln)

    fl.close()

    if (not testls):
        raise Exception('Source file contains no tests')
    return testls


def list_commands(ls, res=None, nested=()):
    """Given a list of commands, replace any {include} commands with the
    commands in the named subtests. This works recursively.
    """
    if res is None:
        res = []
    for cmd in ls:
        if cmd.type == 'include':
            if cmd.cmd in nested:
                raise Exception('Included test includes itself: %s' % (cmd.cmd,))
            test = testmap.get(cmd.cmd)
            if not test:
                raise Exception('Included test not found: %s' % (cmd.cmd,))
            list_commands(test.cmds, res, nested+(cmd.cmd,))
            continue
        res.append(cmd)
    return res

class VitalCheckException(Exception):
    pass

def run(test, gamefile):
    """Run a single RegTest.
    """
    global totalerrors

    testgamefile = gamefile
    if (test.gamefile):
        testgamefile = test.gamefile
    testterppath, testterpargs = (terppath, terpargs)
    if (test.terp):
        testterppath, testterpargs = test.terp
    
    print('* ' + test.name)
    args = [ testterppath ] + testterpargs + [ testgamefile ]
    proc = subprocess.Popen(args,
                            bufsize=0,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    gamestate = GameStateRemGlk(proc.stdin, proc.stdout)


    cmdlist = list_commands(precommands + test.cmds)

    try:
        gamestate.initialize()
        gamestate.accept_output()
        if (test.precmd):
            for check in test.precmd.checks:
                res = check.eval(gamestate)
                if (res):
                    totalerrors += 1
                    val = '*** ' if opts.verbose else ''
                    print('%s%s: %s' % (val, check, res))
                    if check.vital:
                        raise VitalCheckException()
    
        for cmd in cmdlist:
            if (opts.verbose):
                if cmd.type == 'line':
                    # The input line is echoed by the game.
                    print('>', end='')
                else:
                    print('> {%s} %s' % (cmd.type, repr(cmd.cmd),))
            gamestate.perform_input(cmd)
            gamestate.accept_output()
            for check in cmd.checks:
                res = check.eval(gamestate)
                if (res):
                    totalerrors += 1
                    val = '*** ' if opts.verbose else ''
                    print('%s%s: %s' % (val, check, res))
                    if check.vital:
                        raise VitalCheckException()

    except VitalCheckException as ex:
        # An error has already been logged; just fall out.
        pass
    except Exception as ex:
        totalerrors += 1
        val = '*** ' if opts.verbose else ''
        print('%s%s: %s' % (val, ex.__class__.__name__, ex))

    gamestate = None
    proc.stdin.close()
    proc.stdout.close()
    proc.kill()
    proc.poll()
    

# Compile a test file with the Inform 6 compiler. Return the filename
# of the compiled game file.
def compile_testfile(filename, targetarg):
    suffix = '.ulx'
    if targetarg == '-~G':
        suffix = '.z5'
        
    if filename.endswith('.inf'):
        outname = filename[:-4] + suffix
    else:
        outname = filename + suffix
        
    args = [ opts.compilerpath, targetarg ]
    if (opts.librarypath):
        args.append('+'+opts.librarypath)
    args.append(filename)
    args.append(outname)

    print('Compiling %s...' % (filename,))
    subprocess.check_call(args)

    return outname

if (opts.terppath):
    terppath = opts.terppath
if (not terppath):
    print('No interpreter path specified')
    sys.exit(-1)

targetarg = '-G'
if opts.zcodemode and opts.glulxmode:
    raise Exception('Cannot specify both -G and -Z')
if opts.zcodemode:
    targetarg = '-~G'
    
# We'll need a global testmap for the list_commands call, which substitutes
# includes.
testmap = None

for arg in args:
    try:
        testls = parse_testfile(arg)
        testmap = dict([(test.name, test) for test in testls])
        gamefile = compile_testfile(arg, targetarg)
        for test in testls:
            run(test, gamefile)
        testmap = None
    except Exception as ex:
        print('EXCEPTION: %s: %s' % (arg, ex,))
        totalerrors += 1

if (totalerrors):
    print()
    print('FAILED: %d errors' % (totalerrors,))
