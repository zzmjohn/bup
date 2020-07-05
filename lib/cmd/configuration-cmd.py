#!/bin/sh
"""": # -*-python-*-
# https://sourceware.org/bugzilla/show_bug.cgi?id=26034
export "BUP_ARGV_0"="$0"
arg_i=1
for arg in "$@"; do
    export "BUP_ARGV_${arg_i}"="$arg"
    shift
    arg_i=$((arg_i + 1))
done
# Here to end of preamble replaced during install
bup_python="$(dirname "$0")/../../config/bin/python" || exit $?
exec "$bup_python" "$0"
"""
# end of bup preamble

from __future__ import absolute_import, print_function
import os.path, sys

sys.path[:0] = [os.path.dirname(os.path.realpath(__file__)) + '/..']

from bup import _helpers, compat, options, version
from bup.io import byte_stream

out = None

def show_support(out, bool_opt, what):
    if bool_opt:
        out.write(b'    Supports %s\n' % what)
    else:
        out.write(b'    Does not support %s\n' % what)

optspec = """
bup configuration
"""
o = options.Options(optspec)
opt, flags, extra = o.parse(compat.argv[1:])

sys.stdout.flush()
out = byte_stream(sys.stdout)

out.write(b'bup %s\n' % version.version)
out.write(b'source %s %s\n' % (version.commit, version.date))

have_readline = getattr(_helpers, 'readline', None)
have_libacl = getattr(_helpers, 'read_acl', None)

show_support(out, have_readline, b'command line editing (e.g. bup ftp)')
show_support(out, have_libacl, b'saving and restoring POSIX ACLs')
