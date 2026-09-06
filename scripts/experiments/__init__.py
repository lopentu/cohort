"""The experiments behind the numbers in the PNC talk, as runnable scripts.

Each script prints the table it is responsible for and nothing else; the
README in this folder maps every quoted number to the command that produces
it. They read Radich's data from the folder given on the command line (never
committed) and reuse `cohort.attribution` for parsing, profiling and the
withholding rule, so a change there changes these numbers too -- which is the
point: a number in a slide should have one implementation behind it.
"""
