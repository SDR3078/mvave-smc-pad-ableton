import Live
from .MVave_SMC_STEPSEQ import MVave_SMC_STEPSEQ


def create_instance(c_instance):
    """ Creates and returns the M-Vave SMC-PAD step sequencer script """
    return MVave_SMC_STEPSEQ(c_instance)

# local variables:
# tab-width: 4
