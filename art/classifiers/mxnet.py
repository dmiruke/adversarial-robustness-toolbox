from __future__ import absolute_import, division, print_function, unicode_literals

import six
import numpy as np

from art.classifiers import Classifier


class MXClassifier(Classifier):
    def __init__(self, clip_values, model, input_shape, nb_classes, optimizer=None, ctx=None, channel_index=1,
                 defences=None, preprocessing=(0, 1)):
        """
        Initialize an `MXClassifier` object. Assumes the `model` passed as parameter is a Gluon model and that the
        loss function is the softmax cross-entropy.

        :param clip_values: Tuple of the form `(min, max)` representing the minimum and maximum values allowed
               for features.
        :type clip_values: `tuple`
        :param model: The model with logits as expected output.
        :type model: `mxnet.gluon.Block`
        :param input_shape: The shape of one input instance.
        :type input_shape: `tuple`
        :param nb_classes: The number of classes of the model.
        :type nb_classes: `int`
        :param optimizer: The optimizer used to train the classifier. This parameter is not required if no training is
               used.
        :type optimizer: `mxnet.gluon.Trainer`
        :param ctx: The device on which the model runs (CPU or GPU). If not provided, CPU is assumed.
        :type ctx: `mxnet.context.Context`
        :param channel_index: Index of the axis in data containing the color channels or features.
        :type channel_index: `int`
        :param defences: Defences to be activated with the classifier.
        :type defences: `str` or `list(str)`
        :param preprocessing: Tuple of the form `(substractor, divider)` of floats or `np.ndarray` of values to be
               used for data preprocessing. The first value will be substracted from the input. The input will then
               be divided by the second one.
        :type preprocessing: `tuple`
        """
        import mxnet as mx

        super(MXClassifier, self).__init__(clip_values=clip_values, channel_index=channel_index, defences=defences,
                                           preprocessing=preprocessing)

        self._model = model
        self._nb_classes = nb_classes
        self._input_shape = input_shape
        self._device = ctx
        self._optimizer = optimizer

        if ctx is None:
            self._ctx = mx.cpu()
        else:
            self._ctx = ctx

        # Get the internal layer
        self._layer_names = self._get_layers()

    def fit(self, x, y, batch_size=128, nb_epochs=20):
        """
        Fit the classifier on the training set `(inputs, outputs)`.

        :param x: Training data.
        :type x: `np.ndarray`
        :param y: Labels, one-vs-rest encoding.
        :type y: `np.ndarray`
        :param batch_size: Size of batches.
        :type batch_size: `int`
        :param nb_epochs: Number of epochs to use for trainings.
        :type nb_epochs: `int`
        :return: `None`
        """
        if self._optimizer is None:
            raise ValueError()

        from mxnet import autograd, nd

        # Apply preprocessing and defences
        x_ = self._apply_processing(x)
        x_, y_ = self._apply_defences_fit(x_, y)
        y_ = np.argmax(y_, axis=1)

        nb_batch = int(np.ceil(len(x_) / batch_size))
        ind = np.arange(len(x_))

        for _ in range(nb_epochs):
            # Shuffle the examples
            np.random.shuffle(ind)

            # Train for one epoch
            for m in range(nb_batch):
                x_batch = nd.array(x_[ind[m * batch_size:(m + 1) * batch_size]])
                y_batch = nd.array(y_[ind[m * batch_size:(m + 1) * batch_size]])

                with autograd.record(train_mode=True):
                    preds = self._model(x_batch)
                    loss = nd.softmax_cross_entropy(preds, y_batch)
                loss.backward()

                # Update parameters
                self._optimizer.step(batch_size)

    def predict(self, x, logits=False):
        """
        Perform prediction for a batch of inputs.

        :param x: Test set.
        :type x: `np.ndarray`
        :param logits: `True` if the prediction should be done at the logits layer.
        :type logits: `bool`
        :return: Array of predictions of shape `(nb_inputs, self.nb_classes)`.
        :rtype: `np.ndarray`
        """
        from mxnet import autograd, nd

        # Apply preprocessing and defences
        x_ = self._apply_processing(x)
        x_ = self._apply_defences_predict(x_)

        # Predict
        # TODO add batching?
        x_ = nd.array(x_, ctx=self._ctx)
        x_.attach_grad()
        with autograd.record(train_mode=False):
            preds = self._model(x_)

        if logits is True:
            preds = preds.softmax()

        # preds = np.empty((x.shape[0], self.nb_classes), dtype=float)
        # pred_iter = mx.io.NDArrayIter(data=x_, batch_size=128)
        # if logits is True:
        #     for preds_i, i, batch in mod.iter_predict(pred_iter):
        #         pred_label = preds_i[0].asnumpy()
        # else:
        #     for preds_i, i, batch in mod.iter_predict(pred_iter):
        #         pred_label = preds_i[0].softmax().asnumpy()

        return preds.asnumpy()

    def class_gradient(self, x, label=None, logits=False):
        """
        Compute per-class derivatives w.r.t. `x`.

        :param x: Sample input with shape as expected by the model.
        :type x: `np.ndarray`
        :param label: Index of a specific per-class derivative. If `None`, then gradients for all
                      classes will be computed.
        :type label: `int`
        :param logits: `True` if the prediction should be done at the logits layer.
        :type logits: `bool`
        :return: Array of gradients of input features w.r.t. each class in the form
                 `(batch_size, nb_classes, input_shape)` when computing for all classes, otherwise shape becomes
                 `(batch_size, 1, input_shape)` when `label` parameter is specified.
        :rtype: `np.ndarray`
        """
        raise NotImplementedError
        # from mxnet import autograd, nd
        #
        # if label is not None and label not in range(self._nb_classes):
        #     raise ValueError('Label %s is out of range.' % label)
        #
        # x_ = self._apply_processing(x)
        # x_ = nd.array(x_, ctx=self._ctx)
        #
        # for i in range(self.nb_classes):
        #     x_.attach_grad()
        #     with autograd.record(train_mode=False):
        #         if logits is True:
        #             preds = self._model(x_)
        #         else:
        #             preds = self._model(x_).softmax()
        #
        #     preds[:, 0].backward(retain_graph=True, train_mode=False)
        #     # print(i, x_.grad.asnumpy().shape)
        #     # exit()
        # grads = np.swapaxes(grads.asnumpy(), 0, 1)
        # grads = self._apply_processing_gradient(grads)
        #
        # return grads

    def loss_gradient(self, x, y):
        """
        Compute the gradient of the loss function w.r.t. `x`.

        :param x: Sample input with shape as expected by the model.
        :type x: `np.ndarray`
        :param y: Correct labels, one-vs-rest encoding.
        :type y: `np.ndarray`
        :return: Array of gradients of the same shape as `x`.
        :rtype: `np.ndarray`
        """
        from mxnet import autograd, gluon, nd

        x_ = nd.array(x, ctx=self._ctx)
        y_ = nd.array([np.argmax(y, axis=1)]).T

        x_.attach_grad()
        loss = gluon.loss.SoftmaxCrossEntropyLoss()
        with autograd.record(train_mode=False):
            preds = self._model(x_)
            loss = loss(preds, y_)
            loss.backward()
        grads = x_.grad.asnumpy()
        grads = self._apply_processing_gradient(grads)
        assert grads.shape == x.shape

        return grads

    @property
    def layer_names(self):
        """
        Return the hidden layers in the model, if applicable.

        :return: The hidden layers in the model, input and output layers excluded.
        :rtype: `list`

        .. warning:: `layer_names` tries to infer the internal structure of the model.
                     This feature comes with no guarantees on the correctness of the result.
                     The intended order of the layers tries to match their order in the model, but this is not
                     guaranteed either.
        """
        return self._layer_names

    def get_activations(self, x, layer):
        """
        Return the output of the specified layer for input `x`. `layer` is specified by layer index (between 0 and
        `nb_layers - 1`) or by name. The number of layers can be determined by counting the results returned by
        calling `layer_names`.

        :param x: Input for computing the activations.
        :type x: `np.ndarray`
        :param layer: Layer for computing the activations
        :type layer: `int` or `str`
        :return: The output of `layer`, where the first dimension is the batch size corresponding to `x`.
        :rtype: `np.ndarray`
        """
        from mxnet import nd

        if isinstance(layer, six.string_types):
            if layer not in self._layer_names:
                raise ValueError('Layer name %s is not part of the model.' % layer)
            layer_ind = self._layer_names.index(layer)
        elif type(layer) is int:
            if layer < 0 or layer >= len(self._layer_names):
                raise ValueError('Layer index %d is outside of range (0 to %d included).'
                                 % (layer, len(self._layer_names) - 1))
            layer_ind = layer
        else:
            raise TypeError('Layer must be of type `str` or `int`.')

        # Apply preprocessing and defences
        if x.shape == self.input_shape:
            x_ = np.expand_dims(x, 0)
        else:
            x_ = x
        x_ = self._apply_processing(x_)
        x_ = self._apply_defences_predict(x_)

        # Compute activations
        x_ = nd.array(x_, ctx=self._ctx)
        preds = self._model[layer_ind](x_)

        return preds.asnumpy()

    def _get_layers(self):
        """
        Return the hidden layers in the model, if applicable.

        :return: The hidden layers in the model, input and output layers excluded.
        :rtype: `list`
        """

        layer_names = [layer.name for layer in self._model[:-1]]
        return layer_names
