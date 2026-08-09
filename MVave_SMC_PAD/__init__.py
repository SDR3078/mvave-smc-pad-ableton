import Live
from .MVave_SMC_PAD import MVave_SMC_PAD


def create_instance(c_instance):
    """ Creates and returns the M-Vave SMC-PAD script """
    return MVave_SMC_PAD(c_instance)

# local variables:
# tab-width: 4
