import Live
from .smc_stepseq import SMCStepSeq


def create_instance(c_instance):
    """ Creates and returns the M-Vave SMC-PAD step sequencer script """
    return SMCStepSeq(c_instance)

# local variables:
# tab-width: 4
