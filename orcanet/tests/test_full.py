#!/usr/bin/env python
# -*- coding: utf-8 -*-
""" Run a test of the entire code on dummy data. """
import numpy as np
import h5py
import os
import shutil
from keras.models import Model
from keras.layers import Dense, Input, Flatten, Convolution3D
from unittest import TestCase

from orcanet.core import Organizer
from orcanet.model_builder import ModelBuilder
from orcanet_contrib.custom_objects import get_custom_objects


class DatasetTest(TestCase):
    """ Tests which require a dataset. """
    def setUp(self):
        """
        Make a .temp directory in the current working directory, generate
        dummy data in it and set up the cfg object.

        """
        # Pathes
        # Temporary output folder
        self.temp_dir = os.path.join(os.getcwd(), ".temp/")
        self.output_folder = self.temp_dir + "model/"

        # Pathes to temp dummy data that will get generated
        train_inp = (self.temp_dir + "train1.h5", self.temp_dir + "train2.h5")
        self.train_pathes = {"testing_input": train_inp}

        val_inp = (self.temp_dir + "val1.h5", self.temp_dir + "val2.h5")
        self.val_pathes = {"testing_input": val_inp}

        # The config file to load
        self.data_folder = os.path.join(os.path.dirname(__file__), "data")
        config_file = os.path.join(self.data_folder, "config_test.toml")

        # Make sure temp dir does either not exist or is empty
        if os.path.exists(self.temp_dir):
            assert len(os.listdir(self.temp_dir)) == 0
        else:
            os.makedirs(self.temp_dir)

        # Make dummy data of given shape
        self.shape = (3, 3, 3, 3)
        for path1, path2 in (train_inp, val_inp):
            make_dummy_data(path1, path2, self.shape)

        def make_orga():
            orga = Organizer(self.output_folder, config_file=config_file)
            orga.cfg._train_files = self.train_pathes
            orga.cfg._val_files = self.val_pathes
            orga.cfg._list_file = "test.toml"
            orga.cfg.zero_center_folder = self.temp_dir
            orga.cfg.label_modifier = label_modifier
            orga.cfg.custom_objects = get_custom_objects()
            return orga

        self.make_orga = make_orga

    def tearDown(self):
        """ Remove the .temp directory. """
        shutil.rmtree(self.temp_dir)

    def test_zero_center(self):
        """ Calculate the zero center image and check if it works properly. """
        orga = self.make_orga()
        xs_mean = orga.get_xs_mean()
        target_xs_mean = np.ones(self.shape)/4
        self.assertTrue(np.allclose(xs_mean["testing_input"], target_xs_mean))

        file = orga.cfg.zero_center_folder + orga.cfg._list_file + '_input_' + "testing_input" + '.npz'
        zero_center_used_ip_files = np.load(file)['zero_center_used_ip_files']
        self.assertTrue(np.array_equal(zero_center_used_ip_files, orga.cfg._train_files["testing_input"]))

    def test_multi_input_model(self):
        """
        Make a model and train it with the test toml files provided to check
        if it throws an error. Also resumes training after the first epoch
        with a custom lr to check if that works.
        """
        orga = self.make_orga()

        model_file = os.path.join(self.data_folder, "model_test.toml")
        builder = ModelBuilder(model_file)
        initial_model = builder.build(orga)

        orga.train(initial_model, epochs=2)

        def test_learning_rate(epoch, fileno):
            lr = (1 + epoch)*(1 + fileno) * 0.001
            return lr

        def test_modifier(xs):
            xs = {key: xs[key] * 2 for key in xs}
            return xs

        orga = self.make_orga()
        orga.cfg.learning_rate = test_learning_rate
        orga.cfg.sample_modifier = test_modifier
        orga.train(epochs=1)
        orga.predict()

    def test_model_setup_CNN_model(self):
        orga = self.make_orga()
        model_file = os.path.join(self.data_folder, "model_CNN.toml")
        builder = ModelBuilder(model_file)
        model = builder.build(orga)

        self.assertEqual(model.input_shape[1:], self.shape)
        self.assertEqual(model.output_shape[1:], (2, ))
        self.assertEqual(len(model.layers), 14)

    def test_merge_models(self):
        def build_model(inp_layer_name, inp_shape):
            inp = Input(inp_shape, name=inp_layer_name)
            x = Convolution3D(3, 3)(inp)
            x = Flatten()(x)
            out = Dense(1, name="out_0")(x)

            model = Model(inp, out)
            return model

        model_file = os.path.join(self.data_folder, "model_CNN.toml")
        builder = ModelBuilder(model_file)
        model1 = build_model("inp_A", self.shape)
        model2 = build_model("inp_B", self.shape)
        merged_model = builder.merge_models([model1, model2])

        for layer in model1.layers + model2.layers:
            if isinstance(layer, Dense):
                continue
            merged_layer = merged_model.get_layer(layer.name)
            for i in range(len(layer.get_weights())):
                self.assertTrue(np.array_equal(layer.get_weights()[i],
                                               merged_layer.get_weights()[i]))


def make_dummy_data(filepath1, filepath2, shape):
    """
    Make a total of 100 ones vs 300 zeroes of dummy data over two files.

    Parameters
    ----------
    filepath1 : str
        Path to file 1.
    filepath2 : str
        Path to file 2.
    shape : tuple
        Shape of the data, not including sample dimension.

    """
    xs1 = np.concatenate([np.ones((75,) + shape), np.zeros((75,) + shape)])
    xs2 = np.concatenate([np.ones((25,) + shape), np.zeros((225,) + shape)])

    dtypes = [('event_id', '<f8'), ('particle_type', '<f8'), ('energy', '<f8'),
              ('is_cc', '<f8'), ('bjorkeny', '<f8'), ('dir_x', '<f8'),
              ('dir_y', '<f8'), ('dir_z', '<f8'), ('time_interaction', '<f8'),
              ('run_id', '<f8'), ('vertex_pos_x', '<f8'), ('vertex_pos_y', '<f8'),
              ('vertex_pos_z', '<f8'), ('time_residual_vertex', '<f8'),
              ('prod_ident', '<f8'), ('group_id', '<i8')]
    ys1 = np.ones((150, 16)).ravel().view(dtype=dtypes)
    ys2 = np.ones((250, 16)).ravel().view(dtype=dtypes)

    for xs, ys, filepath in ((xs1, ys1, filepath1), (xs2, ys2, filepath2)):
        h5f = h5py.File(filepath, 'w')
        h5f.create_dataset('x', data=xs, dtype='uint8')
        h5f.create_dataset('y', data=ys, dtype=dtypes)
        h5f.close()


def label_modifier(y_values):
    ys = dict()

    ys['dx'], ys['dx_err'] = y_values['dir_x'], y_values['dir_x']

    for key_label in ys:
        ys[key_label] = ys[key_label].astype(np.float32)
    return ys


def make_dummy_model(shape):
    inp = Input(shape=shape)
    x = Flatten()(inp)
    x = Dense(5)(x)
    model = Model(inp, x)
    model.compile("sgd", loss="mse")
    return model