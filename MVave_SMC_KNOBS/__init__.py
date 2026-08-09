import Live
from .MVave_SMC_KNOBS import MVave_SMC_KNOBS


def create_instance(c_instance):
    """ Creates and returns the M-Vave SMC-PAD encoder script """
    return MVave_SMC_KNOBS(c_instance)

# local variables:
# tab-width: 4
