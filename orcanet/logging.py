"""
Logging and keras Callback classes.
"""

import numpy as np
import os
import keras as ks


class SummaryLogger:
    """
    For managing the summary and training logfiles made during orga train.
    """
    def __init__(self, orga, model=None):
        """
        Init with the training files in orga, and metrics in the model.

        Parameters
        ----------
        orga : object Organizer
            Contains all the configurable options in the OrcaNet scripts.
        model : ks.model.Model or None
            Keras model containing the metrics to plot. Required for
            writing new lines, but not for read-out.

        """

        # Minimum width of the cells in characters.
        self.minimum_cell_width = 9
        # Precision to which floats are rounded if they appear in data.
        self.float_precision = 4

        self.logfile_name = orga.cfg.output_folder + 'summary.txt'
        self.train_log_folder = orga.io.get_subfolder("train_log")

        if model is not None:
            self.metric_names = model.metrics_names
            # calculate the fraction of samples per file compared to all files,
            # e.g. [100, 50, 50] --> [0.5, 0.75, 1]
            file_sizes = orga.io.get_file_sizes("train")
            self.file_sizes_rltv = np.cumsum(file_sizes) / np.sum(file_sizes)
        else:
            self.metric_names = None
            self.file_sizes_rltv = None

    def _init_writing(self):
        """
        Get the widths of the columns, and write the head if the file is new.

        The widths have the length of the metric names, but at least the
        self.minimum_cell_width.

        Returns
        -------
        widths : list
            The width of every cell in characters.

        """
        if self.metric_names is None or self.file_sizes_rltv is None:
            raise AttributeError("Can not write logfile: "
                                 "No model given during initialization. ")
        # content of the headline of the file
        data = ["Epoch", "LR", ]
        for i, metric_name in enumerate(self.metric_names):
            data.append("train_" + str(metric_name))
            data.append("val_" + str(metric_name))

        headline, widths = self._get_line(data)
        if not os.path.isfile(self.logfile_name) or \
                os.stat(self.logfile_name).st_size == 0:
            with open(self.logfile_name, 'a+') as logfile:
                # Write the two headlines if the file is empty
                logfile.write(headline + "\n")

                vline = ["-" * width for width in widths]
                vertical_line = self._get_line(vline, widths, seperator="-+-")
                logfile.write(vertical_line + "\n")

        return widths

    def write_line(self, epoch, lr, history_train, history_val=None):
        """
        Write a line to the summary.txt file in every trained model folder.

        Parameters
        ----------
        epoch : tuple(int, int)
            The number of the current epoch and the current filenumber.
        lr : float
            The current learning rate of the model.
        history_train : dict
            Dict containing the history of the training, averaged
            over files.
        history_val : dict or None
            Dict of validation losses for all the metrics, averaged over
            all validation files.

        """
        widths = self._init_writing()

        epoch_float = epoch[0]-1 + self.file_sizes_rltv[epoch[1]-1]

        with open(self.logfile_name, 'a+') as logfile:
            # Write the content: Epoch, LR, train_1, val_1, ...
            data = [epoch_float, lr]
            for i, metric_name in enumerate(self.metric_names):
                data.append(history_train[metric_name])
                if history_val is None:
                    data.append("nan")
                else:
                    data.append(history_val[metric_name])

            line = self._get_line(data, widths)
            logfile.write(line + '\n')

    def _get_line(self, data, widths=None, seperator=" | "):
        """
        Get a line in the proper format for the summary plot,
        consisting of multiple spaced and seperated cells.

        Parameters
        ----------
        data : List
            Strings or floats of what is in each cell.
        widths : List or None
            Optional: The width of every cell. If None, will set it
            automatically, depending on the data. If widths is given, but
            what is given in data is wider than the width, the cell will
            expand without notice.
        seperator : str
            String that seperates two adjacent cells.

        Returns
        -------
        line : str
            The line.
        new_widths : List
            Optional: If the input widths were None: The widths of the cells .

        """
        if widths is None:
            new_widths = []

        line = ""
        for i, entry in enumerate(data):
            # no seperator before the first entry
            if i == 0:
                sep = ""
            else:
                sep = seperator

            # If entry is a number, round to given precision and make it a string
            if not isinstance(entry, str):
                entry = format(float(entry), "."+str(self.float_precision)+"g")

            if widths is None:
                cell_width = max(self.minimum_cell_width, len(entry))
                new_widths.append(cell_width)
            else:
                cell_width = widths[i]

            cell_cont = format(entry, "<"+str(cell_width))

            line += "{seperator}{entry}".format(seperator=sep, entry=cell_cont,)

        if widths is None:
            return line, new_widths
        else:
            return line

    def get_summary_data(self):
        """
        Read out the summary file in the output folder.

        Returns
        -------
        summary_data : ndarray
            Numpy structured array with the column names as datatypes.

        """
        summary_data = np.genfromtxt(self.logfile_name, names=True,
                                     delimiter="|", autostrip=True,
                                     comments="--")
        return summary_data

    def get_train_data(self):
        """
        Read out all training logfiles in the output folder.

        Read out the data from the summary.txt file, and from all training
        log files in the train_log folder, which is in the same directory
        as the summary.txt file.

        Returns
        -------
        summary_data : numpy.ndarray
            Structured array containing the data from the summary.txt file.

        """
        # list of all files in the train_log folder of this model
        files = os.listdir(self.train_log_folder)
        train_file_data = []
        for file in files:
            if not (file.startswith("log_epoch_") and file.endswith(".txt")):
                continue
            # file is sth like "log_epoch_1_file_2.txt", extract the 1 and 2:
            epoch, file_no = [int(file.split(".")[0].split("_")[i]) for i in [2, 4]]
            file_data = np.genfromtxt(self.train_log_folder + "/" + file,
                                      names=True, delimiter="\t")
            train_file_data.append([[epoch, file_no], file_data])

        train_file_data.sort()
        full_train_data = train_file_data[0][1]
        for [epoch, file_no], file_data in train_file_data[1:]:
            full_train_data = np.append(full_train_data, file_data)
        return full_train_data


class BatchLogger(ks.callbacks.Callback):
    """
    Write logfiles during training.

    Averages the losses of the model over some number of batches,
    and then writes that in a line in the logfile.
    The Batch_float entry in the logfiles gives the absolute position
    of the batch in the epoch (i.e. taking all files into account).
    This is intended to be used only for one epoch (one file).

    """
    def __init__(self, orga, epoch):
        """

        Parameters
        ----------
        orga : object Organizer
            Contains all the configurable options in the OrcaNet scripts.
        epoch : tuple
            Epoch and file number.

        """
        ks.callbacks.Callback.__init__(self)

        self.epoch_number = epoch[0]
        self.f_number = epoch[1]

        # settings (read from orga)
        self.display = orga.cfg.train_logger_display
        self.flush = orga.cfg.train_logger_flush
        self.logfile_name = '{}/log_epoch_{}_file_{}.txt'.format(
            orga.io.get_subfolder("train_log", create=True),
            self.epoch_number, self.f_number)
        self.batchsize = orga.cfg.batchsize
        self.file_sizes = np.array(orga.io.get_file_sizes("train"))

        # get the total no of batches over all files (not just the current one)
        # This is for calculating the batch_float number in the logs
        file_batches = np.ceil(self.file_sizes / self.batchsize)
        self.total_batches = np.sum(file_batches)
        # no of batches seen in previous files
        if self.f_number == 1:
            self.previous_batches = 0.
        elif self.f_number > 1:
            self.previous_batches = np.cumsum(file_batches)[self.f_number - 2]
        else:
            raise AssertionError("f_number not >= 1 ({})".format(self.f_number))

        self.seen = None
        self.lines = None
        self.cum_metrics = None

    def on_epoch_begin(self, epoch, logs=None):
        # no of seen batches in this epoch
        self.seen = 0
        # list of stored lines, so that multiple can be written at once
        self.lines = []
        # store the various metrices to be able to average over multiple batches
        self.cum_metrics = {}
        for metric in self.model.metrics_names:
            self.cum_metrics[metric] = 0
        self._write_head()

    def on_batch_end(self, batch, logs=None):
        # self.params:
        #   {'epochs': 1, 'steps': 50, 'verbose': 1, 'do_validation': False,
        #    'metrics': ['loss', 'dx_loss', 'dx_err_loss',
        #    'val_loss', 'val_dx_loss', 'val_dx_err_loss']}
        # logs:
        #   {'batch': 7, 'size': 5, 'loss': 2.06344,
        #    'dx_loss': 0.19809794, 'dx_err_loss': 0.08246058}
        logs = logs or {}

        self.seen += 1
        for metric in self.model.metrics_names:
            self.cum_metrics[metric] += logs.get(metric)

        if self.seen % self.display == 0:
            # The fraction is shifted by self.display / 2., so that it is in
            # the middle of the samples
            batch_frctn = self.epoch_number - 1 + (
                    self.previous_batches + self.seen
                    - self.display / 2.) / self.total_batches

            line = '\n{0}\t{1}'.format(int(self.seen), batch_frctn)
            for metric in self.model.metrics_names:
                line = line + '\t' + str(self.cum_metrics[metric] / self.display)
                self.cum_metrics[metric] = 0
            self.lines.append(line)

            flush = self.flush != -1 and self.display % self.flush == 0
            self._write_lines(flush)

    def on_epoch_end(self, batch, logs=None):
        # on epoch end here means that this is called after one fit_generator
        # loop in Keras is finished, so after one file in our case.
        self._write_lines(True)

    def _write_lines(self, flush=False):
        """ Write lines in self.lines and empty it. """
        with open(self.logfile_name, 'a') as file:
            for line in self.lines:
                file.write(line)
            if flush:
                file.flush()
                os.fsync(file.fileno())
        self.lines = []

    def _write_head(self):
        """ write column names for all losses / metrics """
        with open(self.logfile_name, 'w') as file:
            file.write('Batch\tBatch_float\t')
            for i, metric in enumerate(self.model.metrics_names):
                file.write(metric)
                if i + 1 < len(self.model.metrics_names):
                    file.write('\t')


# class TensorBoardWrapper(ks.callbacks.TensorBoard):
#     """Up to now (05.10.17), Keras doesn't accept TensorBoard callbacks with validation data that is fed by a generator.
#      Supplying the validation data is needed for the histogram_freq > 1 argument in the TB callback.
#      Without a workaround, only scalar values (e.g. loss, accuracy) and the computational graph of the model can be saved.
#
#      This class acts as a Wrapper for the ks.callbacks.TensorBoard class in such a way,
#      that the whole validation data is put into a single array by using the generator.
#      Then, the single array is used in the validation steps. This workaround is experimental!"""
#     def __init__(self, batch_gen, nb_steps, **kwargs):
#         super(TensorBoardWrapper, self).__init__(**kwargs)
#         self.batch_gen = batch_gen # The generator.
#         self.nb_steps = nb_steps   # Number of times to call next() on the generator.
#
#     def on_epoch_end(self, epoch, logs):
#         # Fill in the `validation_data` property.
#         # After it's filled in, the regular on_epoch_end method has access to the validation_data.
#         imgs, tags = None, None
#         for s in range(self.nb_steps):
#             ib, tb = next(self.batch_gen)
#             if imgs is None and tags is None:
#                 imgs = np.zeros(((self.nb_steps * ib.shape[0],) + ib.shape[1:]), dtype=np.float32)
#                 tags = np.zeros(((self.nb_steps * tb.shape[0],) + tb.shape[1:]), dtype=np.uint8)
#             imgs[s * ib.shape[0]:(s + 1) * ib.shape[0]] = ib
#             tags[s * tb.shape[0]:(s + 1) * tb.shape[0]] = tb
#         self.validation_data = [imgs, tags, np.ones(imgs.shape[0]), 0.0]
#         return super(TensorBoardWrapper, self).on_epoch_end(epoch, logs)
