#  Copyright 2016 The TensorFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
"""Example of Estimator for CNN-based text classification with DBpedia data."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import sys

import numpy as np
import pandas
from sklearn import metrics
import tensorflow as tf

FLAGS = None

MAX_DOCUMENT_LENGTH = 100
EMBEDDING_SIZE = 20
N_FILTERS = 10
POOLING_WINDOW = 4
POOLING_STRIDE = 2
n_words = 0
MAX_LABEL = 15
WORDS_FEATURE = 'words'  # Name of the input words feature.
filter_list = [3, 4, 5]


def print_operation(t):
    print(t.op.name, ' ', t.get_shape().as_list())

# 两种size的Conv+Max 依次处理
def cnn_model(features, labels, mode):
    """2 layer ConvNet to predict from sequence of words to a class."""
    # Convert indexes of words into embeddings.
    # This creates embeddings matrix of [n_words, EMBEDDING_SIZE] and then
    # maps word indexes of the sequence into [batch_size, sequence_length,
    # EMBEDDING_SIZE].
    word_vectors = tf.contrib.layers.embed_sequence(
        features[WORDS_FEATURE], vocab_size=n_words, embed_dim=EMBEDDING_SIZE)
    word_vectors = tf.expand_dims(word_vectors, 3)
    net = None

    for window_size in filter_list:
        filter_shape = [window_size, EMBEDDING_SIZE]
        with tf.variable_scope('CNN_Layer_%s' % window_size):
            # Apply Convolution filtering on input sequence.
            net = tf.layers.conv2d(
                word_vectors,
                filters=N_FILTERS,
                kernel_size=filter_shape,
                padding='VALID',
                # Add a ReLU for non linearity.
                activation=tf.nn.relu)
            # Max pooling across output of Convolution+Relu.
            print_operation(net)
            net = tf.layers.max_pooling2d(
                net,
                pool_size=POOLING_WINDOW,
                strides=POOLING_STRIDE,
                padding='SAME')
            print_operation(net)
            # Transpose matrix so that n_filters from convolution becomes width.
            net = tf.transpose(net, [0, 1, 3, 2])
            print_operation(net)

    net = tf.transpose(net, [0, 1, 3, 2])
    print_operation(net)

    # Max across each filter to get useful features for classification.
    net = tf.squeeze(tf.reduce_max(net, 1), squeeze_dims=[1])
    # print_operation(net)
    # Apply regular WX + B and classification.
    logits = tf.layers.dense(net, MAX_LABEL, activation=None)
    predicted_classes = tf.argmax(logits, 1)
    if mode == tf.estimator.ModeKeys.PREDICT:
        return tf.estimator.EstimatorSpec(
            mode=mode,
            predictions={
                'class': predicted_classes,
                'prob': tf.nn.softmax(logits)
            })

    onehot_labels = tf.one_hot(labels, MAX_LABEL, 1, 0)
    loss = tf.losses.softmax_cross_entropy(
        onehot_labels=onehot_labels, logits=logits)
    if mode == tf.estimator.ModeKeys.TRAIN:
        optimizer = tf.train.AdamOptimizer(learning_rate=0.01)
        train_op = optimizer.minimize(loss, global_step=tf.train.get_global_step())
        return tf.estimator.EstimatorSpec(mode, loss=loss, train_op=train_op)

    eval_metric_ops = {
        'accuracy': tf.metrics.accuracy(
            labels=labels, predictions=predicted_classes)
    }
    return tf.estimator.EstimatorSpec(
        mode=mode, loss=loss, eval_metric_ops=eval_metric_ops)


def main(unused_argv):
    global n_words
    # Prepare training and testing data
    dbpedia = tf.contrib.learn.datasets.load_dataset(
        'dbpedia', test_with_fake_data=FLAGS.test_with_fake_data)
    x_train = pandas.DataFrame(dbpedia.train.data)[1]
    y_train = pandas.Series(dbpedia.train.target)
    x_test = pandas.DataFrame(dbpedia.test.data)[1]
    y_test = pandas.Series(dbpedia.test.target)

    # Process vocabulary
    vocab_processor = tf.contrib.learn.preprocessing.VocabularyProcessor(
        MAX_DOCUMENT_LENGTH)
    x_train = np.array(list(vocab_processor.fit_transform(x_train)))
    x_test = np.array(list(vocab_processor.transform(x_test)))
    n_words = len(vocab_processor.vocabulary_)
    print('Total words: %d' % n_words)

    # Build model
    classifier = tf.estimator.Estimator(model_fn=cnn_model)

    # Train.
    train_input_fn = tf.estimator.inputs.numpy_input_fn(
        x={WORDS_FEATURE: x_train},
        y=y_train,
        batch_size=len(x_train),
        num_epochs=None,
        shuffle=True)
    classifier.train(input_fn=train_input_fn, steps=100)

    # Predict.
    test_input_fn = tf.estimator.inputs.numpy_input_fn(
        x={WORDS_FEATURE: x_test},
        y=y_test,
        num_epochs=1,
        shuffle=False)
    predictions = classifier.predict(input_fn=test_input_fn)
    y_predicted = np.array(list(p['class'] for p in predictions))
    y_predicted = y_predicted.reshape(np.array(y_test).shape)

    # Score with sklearn.
    score = metrics.accuracy_score(y_test, y_predicted)
    print('Accuracy (sklearn): {0:f}'.format(score))

    # Score with tensorflow.
    scores = classifier.evaluate(input_fn=test_input_fn)
    print('Accuracy (tensorflow): {0:f}'.format(scores['accuracy']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--test_with_fake_data',
        default=False,
        help='Test the example code with fake data.',
        action='store_true')
    FLAGS, unparsed = parser.parse_known_args()
    tf.app.run(main=main, argv=[sys.argv[0]] + unparsed)
