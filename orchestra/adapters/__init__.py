"""Adapters: real execution/navigation adapters the kernel shells out to.

These perform actual, evidence-producing operations (Robot run, file/dependency probe).
They never fabricate; a result is only as valid as the subprocess/artifact it returned.
"""
