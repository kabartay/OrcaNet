#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Code for training and validating NN's, as well as evaluating them.
"""

import os
from inspect import signature
import keras.backend as K
import h5py
from contextlib import ExitStack
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from orcanet.utilities.visualization import (
    plot_all_metrics_to_pdf, plot_activations, plot_weights)
from orcanet.logging import SummaryLogger, BatchLogger

# for debugging
# from tensorflow.python import debug as tf_debug
# K.set_session(tf_debug.LocalCLIDebugWrapperSession(tf.Session()))


def train_and_validate_model(orga, model, next_epoch):
    """
    Train a model for one epoch, i.e. on all (remaining) train files once.

    Trains (fit_generator) and validates (evaluate_generator) a Keras model
    on the provided training and validation files for one epoch. The model
    is saved with an automatically generated filename based on the epoch,
    log files are written and summary plots are made.

    Parameters
    ----------
    orga : object Organizer
        Contains all the configurable options in the OrcaNet scripts.
    model : ks.Models.model
        Compiled keras model to use for training and validating.
    next_epoch : tuple
        Upcoming epoch and file number, aka the epoch/fileno that will
        be trained and saved now.

    """
    smry_logger = SummaryLogger(orga, model)
    n_train_files = orga.io.get_no_of_files("train")
    for file_no in range(next_epoch[1], n_train_files + 1):
        # Only the file number changes during training, as this function
        # trains only for one epoch. Both epoch and fileno start from 1!
        curr_epoch = (next_epoch[0], file_no)

        # -------------------- TRAINING -----------------------------
        # update lr, train, save, make history_train
        line = "Training in epoch {} on file {}/{}".format(curr_epoch[0],
                                                           curr_epoch[1],
                                                           n_train_files)
        orga.io.print_log(line)
        orga.io.print_log("-" * len(line))

        lr = get_learning_rate(curr_epoch, orga.cfg.learning_rate,
                               orga.io.get_no_of_files("train"))
        K.set_value(model.optimizer.lr, lr)
        orga.io.print_log("Learning rate is at {}".format(
            K.get_value(model.optimizer.lr)))

        # Train the model on one file and save it afterwards
        model_filename = orga.io.get_model_path(curr_epoch[0], curr_epoch[1])
        if os.path.isfile(model_filename):
            raise NameError("Can not train model in epoch {} file {}, "
                            "this model has already been trained and "
                            "saved!".format(curr_epoch[0], curr_epoch[1]))
        history_train = train_model(orga, model, curr_epoch)
        model.save(model_filename)
        orga.io.print_log("Saved model to " + model_filename + "\n")

        # ------------------- VALIDATION ----------------------------
        # validate and make activation_and_weights plots

        # Validate after every n-th file
        if curr_epoch[1] == n_train_files or \
                (orga.cfg.validate_interval is not None and
                 curr_epoch[1] % orga.cfg.validate_interval == 0):
            line = "Validation"
            orga.io.print_log(line)
            orga.io.print_log("-" * len(line))
            history_val = validate_model(orga, model)
            save_actv_wghts_plot(orga, model, curr_epoch,
                                 samples=orga.cfg.batchsize)
            orga.io.print_log("")
        else:
            history_val = None

        # ------------------- LOGGING ----------------------------
        # write logfiles and make summary plot

        smry_logger.write_line(curr_epoch, lr, history_train, history_val)
        update_summary_plot(orga)


def train_model(orga, model, curr_epoch):
    """
    Trains a model on one file based on the Keras fit_generator method.

    The progress of the training is also logged.

    Parameters
    ----------
    orga : object Organizer
        Contains all the configurable options in the OrcaNet scripts.
    model : ks.model.Model
        Keras model instance of a neural network.
    curr_epoch : tuple(int, int)
        The number of the current epoch and the current filenumber.

    Returns
    -------
    history : dict
        The history of the training on this file. A record of training
        loss values and metrics values.

    """
    assert curr_epoch[1] > 0, "fileno is {}".format(curr_epoch[1])

    files_dict = orga.io.get_file("train", curr_epoch[1] - 1)
    if orga.cfg.n_events is not None:
        # TODO Can throw an error if n_events is larger than the file
        f_size = orga.cfg.n_events  # for testing purposes
    else:
        f_size = orga.io.get_file_sizes("train")[curr_epoch[1] - 1]

    orga.io.print_log('Inputs and files:')
    for input_name, input_file in files_dict.items():
        orga.io.print_log("   {}: \t{}".format(input_name,
                                               os.path.basename(input_file)))

    callbacks = [BatchLogger(orga, curr_epoch), ]
    if orga.cfg.callback_train is not None:
        try:
            callbacks.extend(orga.cfg.callback_train)
        except TypeError:
            callbacks.append(orga.cfg.callback_train)

    training_generator = hdf5_batch_generator(
        orga, files_dict, f_size=f_size,
        zero_center=orga.cfg.zero_center_folder is not None,
        shuffle=orga.cfg.shuffle_train)

    history = model.fit_generator(
        training_generator,
        steps_per_epoch=int(f_size / orga.cfg.batchsize),
        verbose=orga.cfg.verbose_train,
        max_queue_size=orga.cfg.max_queue_size,
        callbacks=callbacks,
        initial_epoch=curr_epoch[0],
        epochs=curr_epoch[0]+1,
    )
    # get a dict with losses and metrics
    # only trained for one epoch, so value is list of len 1
    history = {key: value[0] for key, value in history.history.items()}

    orga.io.print_log('Training results:')
    for metric_name, loss in history.items():
        orga.io.print_log("   {}: \t{}".format(metric_name, loss))

    return history


def validate_model(orga, model):
    """
    Validates a model on all the validation datafiles.

    This is usually done after a session of training has been finished.

    Parameters
    ----------
    orga : object Organizer
        Contains all the configurable options in the OrcaNet scripts.
    model : ks.model.Model
        Keras model instance of a neural network.

    Returns
    -------
    history_val : dict
        The history of the validation on all files. A record of validation
        loss values and metrics values.

    """
    lines = ['Inputs and files:', ]
    for input_name, input_files in orga.io.get_local_files("val").items():
        line = "   " + input_name + ":\t"
        for i, input_file in enumerate(input_files):
            if i != 0:
                line += ", "
            line += os.path.basename(input_file)
        lines.append(line)
    orga.io.print_log(lines)

    # One history for each val file
    histories = []
    f_sizes = orga.io.get_file_sizes("val")

    for i, files_dict in enumerate(orga.io.yield_files("val")):
        f_size = f_sizes[i]
        if orga.cfg.n_events is not None:
            f_size = orga.cfg.n_events  # for testing purposes

        val_generator = hdf5_batch_generator(
            orga, files_dict, f_size=f_size,
            zero_center=orga.cfg.zero_center_folder is not None)

        history = model.evaluate_generator(
            val_generator,
            steps=int(f_size / orga.cfg.batchsize),
            max_queue_size=orga.cfg.max_queue_size,
            verbose=orga.cfg.verbose_val)

        histories.append(history)

    # average over all val files if necessary
    history_val = [sum(col) / float(len(col)) for col in zip(*histories)] \
        if len(histories) > 1 else histories[0]

    # This history is just a list, not a dict like with fit_generator
    # so transform to dict
    history_val = dict(zip(model.metrics_names, history_val))

    orga.io.print_log('Validation results:')
    for metric_name, loss in history_val.items():
        orga.io.print_log("   {}: \t{}".format(metric_name, loss))

    return history_val


def hdf5_batch_generator(orga, files_dict, f_size=None, zero_center=False,
                         yield_mc_info=False, shuffle=False):
    """
    Yields batches of input data from h5 files.

    This will go through one file, or multiple files in parallel, and yield
    one batch of data, which can then be used as an input to a model.
    Since multiple filepaths can be given to read out in parallel,
    this can also be used for models with multiple inputs.

    Parameters
    ----------
    orga : object Organizer
        Contains all the configurable options in the OrcaNet scripts.
    files_dict : dict
        Pathes of the files to train on.
        Keys: The name of every input (from the toml list file, can be multiple).
        Values: The filepath of a single h5py file to read samples from.
    f_size : int or None
        Specifies the number of samples to be read from the .h5 file.
        If none, the whole .h5 file will be used.
    zero_center : bool
        Whether to use zero centering.
        Requires orga.zero_center_folder to be set.
    yield_mc_info : bool
        Specifies if mc-infos (y_values) should be yielded as well. The
        mc-infos are used for evaluation after training and testing is finished.
    shuffle : bool
        Randomize the order in which batches are read from the file.
        Significantly reduces read out speed.

    Yields
    ------
    xs : dict
        Data for the model train on.
            Keys : str  The name(s) of the input layer(s) of the model.
            Values : ndarray    A batch of samples for the corresponding input.
    ys : dict
        Labels for the model to train on.
            Keys : str  The name(s) of the output layer(s) of the model.
            Values : ndarray    A batch of labels for the corresponding output.
    mc_info : ndarray, optional
        Mc info from the file. Only yielded if yield_mc_info is True.

    """
    batchsize = orga.cfg.batchsize
    # name of the datagroups in the file
    samples_key = orga.cfg.key_samples
    mc_key = orga.cfg.key_labels

    # If the batchsize is larger than the f_size, make batchsize smaller
    # or nothing would be yielded
    if f_size is not None:
        if f_size < batchsize:
            batchsize = f_size

    if orga.cfg.label_modifier is not None:
        label_modifier = orga.cfg.label_modifier
    else:
        assert orga._auto_label_modifier is not None, \
            "Auto label modifier has not been set up (can be done with " \
            "nn_utilities.get_auto_label_modifier)"
        label_modifier = orga._auto_label_modifier

    # get xs_mean or load/create if not stored yet
    if zero_center:
        xs_mean = orga.get_xs_mean()
    else:
        xs_mean = None

    with ExitStack() as stack:
        # a dict with the names of list inputs as keys, and the opened
        # h5 files as values
        files = {}
        file_lengths = []
        # open the files and make sure they have the same length
        for input_key in files_dict:
            files[input_key] = stack.enter_context(
                h5py.File(files_dict[input_key], 'r'))
            file_lengths.append(len(files[input_key][samples_key]))

        if not file_lengths.count(file_lengths[0]) == len(file_lengths):
            raise ValueError("All data files must have the same length! "
                             "Yours have:\n " + str(file_lengths))

        if f_size is None:
            f_size = file_lengths[0]
        # number of batches available
        total_no_of_batches = int(np.ceil(f_size/batchsize))
        # positions of the samples in the file
        sample_pos = np.arange(total_no_of_batches) * batchsize
        if shuffle:
            np.random.shuffle(sample_pos)
        # append some samples due to preloading by the fit_generator method
        sample_pos = np.append(sample_pos, sample_pos[:orga.cfg.max_queue_size])

        for sample_n in sample_pos:
            # A dict with every input name as key, and a batch of data as values
            xs = {}
            # Read one batch of samples from the files and zero center
            for input_key in files:
                xs[input_key] = files[input_key][samples_key][
                                sample_n: sample_n + batchsize]
                if xs_mean is not None:
                    xs[input_key] = np.subtract(xs[input_key],
                                                xs_mean[input_key])
            # Get labels for the nn. Since the labels are hopefully the same
            # for all the files, use the ones from the first TODO
            y_values = list(files.values())[0][mc_key][
                       sample_n:sample_n + batchsize]

            # Modify the samples and labels before feeding them into the network
            if orga.cfg.sample_modifier is not None:
                xs = orga.cfg.sample_modifier(xs)

            ys = label_modifier(y_values)

            if not yield_mc_info:
                yield xs, ys
            else:
                yield xs, ys, y_values


def get_learning_rate(epoch, user_lr, no_train_files):
    """
    Get the learning rate for the current epoch and file number.

    Parameters
    ----------
    epoch : tuple
        Epoch and file number.
    user_lr : float or tuple or function.
        The user input for the lr.
    no_train_files : int
        How many train files there are in total.

    Returns
    -------
    lr : float
        The learning rate.

    Raises
    ------
    AssertionError
        If the type of the user_lr is not right.

    """
    error_msg = "The learning rate must be either a float, a tuple of " \
                "two floats or a function."
    try:
        # Float => Constant LR
        lr = float(user_lr)
        return lr
    except (ValueError, TypeError):
        pass

    try:
        # List => Exponentially decaying LR
        length = len(user_lr)
        lr_init = float(user_lr[0])
        lr_decay = float(user_lr[1])
        if length != 2:
            raise TypeError("{} (Your tuple has length {})".format(error_msg,
                                                                   len(user_lr)))

        lr = lr_init * (1 - lr_decay) ** (epoch[1] + epoch[0] * no_train_files)
        return lr
    except (ValueError, TypeError):
        pass

    try:
        # Callable => User defined function
        n_params = len(signature(user_lr).parameters)
        if n_params != 2:
            raise TypeError("A custom learning rate function must have two "
                            "input parameters: The epoch and the file number. "
                            "(yours has {})".format(n_params))
        lr = user_lr(epoch[0], epoch[1])
        return lr
    except (ValueError, TypeError):
        raise TypeError("{} (You gave {} of type {}) ".format(
            error_msg, user_lr, type(user_lr)))


def update_summary_plot(orga):
    """
    Refresh the summary plot of a model directory (plots/summary_plot.pdf).

    Validation and Train-data will be read out automatically, and the loss
    as well as every metric will be plotted in a seperate page in the pdf.

    Parameters
    ----------
    orga : object Organizer
        Contains all the configurable options in the OrcaNet scripts.

    """
    smry_logger = SummaryLogger(orga)
    summary_data = smry_logger.get_summary_data()
    full_train_data = smry_logger.get_train_data()

    pdf_name = orga.io.get_subfolder("plots", create=True) + "/summary_plot.pdf"
    plot_all_metrics_to_pdf(summary_data, full_train_data, pdf_name)


def save_actv_wghts_plot(orga, model, epoch, samples=1):
    """
    Plots the weights of a model and the activations for samples from
    the validation set to one .pdf file each.

    Parameters
    ----------
    orga : object Organizer
        Contains all the configurable options in the OrcaNet scripts.
    model : ks.models.Model
        The model to do the predictions with.
    epoch : tuple
        Current epoch and fileno.
    samples : int
        Number of samples to make the plot for.

    """
    plt.ioff()

    file = next(orga.io.yield_files("val"))
    generator = hdf5_batch_generator(
        orga, file, f_size=samples,
        zero_center=orga.cfg.zero_center_folder is not None,
        yield_mc_info=True)
    xs, ys, y_values = next(generator)

    pdf_name_act = "{}/activations_epoch_{}_file_{}.pdf".format(
        orga.io.get_subfolder("activations", create=True), epoch[0], epoch[1])

    with PdfPages(pdf_name_act) as pdf:
        for layer in model.layers:
            fig = plot_activations(model, xs, layer.name, mode='test')
            pdf.savefig(fig)
            plt.close(fig)

    pdf_name_wght = "{}/weights_epoch_{}_file_{}.pdf".format(
        orga.io.get_subfolder("activations", create=True), epoch[0], epoch[1])

    with PdfPages(pdf_name_wght) as pdf:
        for layer in model.layers:
            fig = plot_weights(model, layer.name)
            if fig is not None:
                pdf.savefig(fig)
                plt.close(fig)


def make_model_prediction(orga, model, eval_filename, samples=None):
    """
    Let a model predict on all validation samples, and save it as a h5 file.

    Per default, the h5 file will contain a datagroup mc_info straight from
    the given files, as well as two datagroups per output layer of the network,
    which have the labels and the predicted values in them as numpy arrays,
    respectively.

    Parameters
    ----------
    orga : object Organizer
        Contains all the configurable options in the OrcaNet scripts.
    model : ks.model.Model
        Trained Keras model of a neural network.
    eval_filename : str
        Name and path of the h5 file.
    samples : int or None
        Number of events that should be predicted.
        If samples=None, the whole file will be used.

    """
    batchsize = orga.cfg.batchsize
    compression = ("gzip", 1)
    file_sizes = orga.io.get_file_sizes("val")
    total_file_size = sum(file_sizes)
    datagroups_created = False

    with h5py.File(eval_filename, 'w') as h5_file:
        # For every val file set (one set can have multiple files if
        # the model has multiple inputs):
        for f_number, files_dict in enumerate(orga.io.yield_files("val")):
            file_size = file_sizes[f_number]
            generator = hdf5_batch_generator(
                orga, files_dict,
                zero_center=orga.cfg.zero_center_folder is not None,
                yield_mc_info=True)

            if samples is None:
                steps = int(file_size / batchsize)
                if file_size % batchsize != 0:
                    # add a smaller step in the end
                    steps += 1
            else:
                steps = int(samples / batchsize)

            for s in range(steps):
                if s % 100 == 0:
                    print('Predicting in step {} on file {}'.format(s, f_number))
                # y_true is a dict of ndarrays, mc_info is a structured
                # array, y_pred is a list of ndarrays
                xs, y_true, mc_info = next(generator)

                y_pred = model.predict_on_batch(xs)
                if not isinstance(y_pred, list):
                    # if only one output, transform to a list
                    y_pred = [y_pred]
                # transform y_pred to dict
                y_pred = {out: y_pred[i] for i, out in enumerate(model.output_names)}

                if orga.cfg.dataset_modifier is None:
                    datasets = get_datasets(mc_info, y_true, y_pred)
                else:
                    datasets = orga.cfg.dataset_modifier(mc_info, y_true, y_pred)

                # TODO maybe add attr to data, like used files or orcanet version number?
                if not datagroups_created:
                    for dataset_name, data in datasets.items():
                        maxshape = (total_file_size,) + data.shape[1:]
                        chunks = True  # (batchsize,) + data.shape[1:]
                        h5_file.create_dataset(
                            dataset_name, data=data, maxshape=maxshape,
                            chunks=chunks, compression=compression[0],
                            compression_opts=compression[1])
                        datagroups_created = True
                else:
                    for dataset_name, data in datasets.items():
                        # append data at the end of the dataset
                        h5_file[dataset_name].resize(
                            h5_file[dataset_name].shape[0] + data.shape[0], axis=0)
                        h5_file[dataset_name][-data.shape[0]:] = data


def get_datasets(mc_info, y_true, y_pred):
    """
    Get the dataset names and numpy array contents.

    Every output layer will get one dataset each for both the label and
    the prediction. E.g. if your model has an output layer called "energy",
    the datasets "label_energy" and "pred_energy" will be made.

    Parameters
    ----------
    mc_info : ndarray
        A structured array containing infos for every event, right from
        the input files.
    y_true : dict
        The labels for each output layer of the network.
    y_pred : dict
        The predictions of each output layer of the network.

    Returns
    -------
    datasets : dict
        Keys are the name of the datagroups, values the content in the
        form of numpy arrays.

    """
    datasets = dict()
    datasets["mc_info"] = mc_info
    for out_layer_name in y_true:
        datasets["label_" + out_layer_name] = y_true[out_layer_name]
    for out_layer_name in y_pred:
        datasets["pred_" + out_layer_name] = y_pred[out_layer_name]
    return datasets
