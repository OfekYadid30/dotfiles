"""Shared library for the git-m* helper scripts (mlog, mfixup, mfixupa, mbranch).

Every executable in ../bin/ is a thin CLI wrapper around this package. Put any
logic that more than one script needs in here instead of copy-pasting it.
"""
