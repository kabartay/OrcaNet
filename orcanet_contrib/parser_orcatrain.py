"""
Use orga.train with a parser.

Usage:
    parser_orcatrain.py [options] FOLDER LIST CONFIG MODEL
    parser_orcatrain.py (-h | --help)

Arguments:
    FOLDER  Path to the folder where everything gets saved to, e.g. the
            summary.txt, the plots, the trained models, etc.
    LIST    A .toml file which contains the pathes of the training and
            validation files. An example can be found in
            examples/example_list.toml
    CONFIG  A .toml file which sets up the training. An example can be
            found in examples/example_config.toml. The possible parameters
            are listed in core.py in the class Configuration.
    MODEL   Path to a .toml file with infos about a model.
            An example can be found in examples/example_model.toml.

Options:
    -h --help    Show this screen.
    --recompile  Recompile the keras model, e.g. needed if the loss weights
                 are changed during the training.

"""
from docopt import docopt
import keras as ks

from orcanet.core import Organizer
from model_builder import ModelBuilder
from orcanet_contrib.orca_handler_util import orca_learning_rates, update_objects


def orca_train(output_folder, list_file, config_file, model_file,
               recompile_model=False):
    """
    Run orga.train with predefined ModelBuilder networks using a parser.

    Parameters
    ----------
    output_folder : str
        Path to the folder where everything gets saved to, e.g. the summary
        log file, the plots, the trained models, etc.
    list_file : str
        Path to a list file which contains pathes to all the h5 files that
        should be used for training and validation.
    config_file : str
        Path to a .toml file which overwrites some of the default settings
        for training and validating a model.
    model_file : str
        Path to a file with parameters to build a model of a predefined
        architecture with OrcaNet.
    recompile_model : bool
        If the model should be recompiled or not. Necessary, if e.g. the
        loss_weights are changed during the training.

    """
    # Set up the Organizer with the input data
    orga = Organizer(output_folder, list_file, config_file)

    # Load in the orga sample-, label-, and dataset-modifiers, as well as
    # the custom objects
    update_objects(orga, model_file)

    # If this is the start of the training, a compiled model needs to be
    # handed to the orga.train function
    if orga.io.is_new():
        # The ModelBuilder class allows to construct models from a toml file,
        # adapted to the datasets in the orga instance. Its modifiers will
        # be taken into account for this
        builder = ModelBuilder(model_file)
        model = builder.build(orga)

    elif recompile_model is True:
        builder = ModelBuilder(model_file)

        path_of_model = orga.io.get_model_path(-1, -1)
        model = ks.models.load_model(path_of_model,
                                     custom_objects=orga.cfg.custom_objects)
        print("Recompiling the saved model")
        model = builder.compile_model(model)

    else:
        model = None

    # Use a custom LR schedule
    orga.cfg.learning_rate = orca_learning_rates("triple_decay",
                                                 orga.io.get_no_of_files("train"))

    # start the training
    orga.train(model=model, force_model=recompile_model)


def parse_input():
    """ Run the orca_train function with a parser. """
    args = docopt(__doc__)
    output_folder = args['FOLDER']
    list_file = args['LIST']
    config_file = args['CONFIG']
    model_file = args['MODEL']
    recompile_model = args['--recompile']
    orca_train(output_folder, list_file, config_file, model_file,
               recompile_model=recompile_model)


if __name__ == '__main__':
    parse_input()
