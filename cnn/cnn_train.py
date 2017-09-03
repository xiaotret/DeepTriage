# -*- coding:utf-8 -*-
import tensorflow as tf
import os
from six.moves import xrange
import data_helpers
import cnn_classification
import argparse
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
FLAGS = None


def train():
    with tf.Graph().as_default():
        session_conf = tf.ConfigProto(
            allow_soft_placement=FLAGS.allow_soft_placement,
            log_device_placement=FLAGS.log_device_placement)
        sess = tf.Session(config=session_conf)
        with sess.as_default():
            tfrecords_files = [os.path.join(
                FLAGS.buckets, "eclipse", 'train%d.tfrecords' % i) for i in range(1, 11)]
            ckpt_path = os.path.join(FLAGS.checkpointDir, "modle.chpt")
            train_log_dir = os.path.join(FLAGS.summaryDir, "train")

            embedding_file_path = os.path.join(FLAGS.buckets, "GoogleNews-vectors-negative300.bin")
            vocab_file_path = os.path.join(FLAGS.buckets, "eclipse", "vocab")
            filename_queue = tf.train.string_input_producer(tfrecords_files)
            train_data, train_labels = data_helpers.read_TFRecord(
                filename_queue, FLAGS.batch_size, shuffle=True)

            embedded_char = cnn_classification.get_embedding(
                train_data, embedding_file_path, FLAGS.embedding_type,
                FLAGS.vocabulary_size, FLAGS.embedding_dim, vocab_file_path)
            dropout_keep_prob = tf.placeholder(tf.float32, name="dropout_keep_prob")
            logits, l2_loss = cnn_classification.inference(embedded_char, list(
                map(int, FLAGS.filter_sizes.split(","))),
                FLAGS.num_filters, FLAGS.num_classes, dropout_keep_prob)
            loss = cnn_classification.loss(logits, train_labels, l2_loss, FLAGS.l2_reg_lambda)
            global_step = tf.contrib.framework.get_or_create_global_step()
            train_op = cnn_classification.train(loss, FLAGS.init_learning_rate, global_step)
            correct, accuracy, precision_op, precision, recall_op, recall = \
                cnn_classification.evaluation(
                    logits, train_labels, FLAGS.top_k)

            merged = tf.summary.merge_all()
            saver = tf.train.Saver()
            writer = tf.summary.FileWriter(train_log_dir, sess.graph)

            # Initialize all variables
            sess.run(tf.global_variables_initializer())
            sess.run(tf.local_variables_initializer())

            # start queue runner
            coord = tf.train.Coordinator()
            threads = tf.train.start_queue_runners(sess=sess, coord=coord)
            num_batches_per_epoch = int((FLAGS.num_train - 1) / FLAGS.batch_size) + 1

            # Train and Test
            for i in xrange(FLAGS.num_epochs):
                for j in xrange(num_batches_per_epoch):
                    _, summary = sess.run([train_op, merged], feed_dict={
                                          dropout_keep_prob: FLAGS.dropout_keep_prob})
                    current_step = tf.train.global_step(sess, global_step)
                    writer.add_summary(summary, current_step)
                    if current_step % FLAGS.evaluate_every == 0:
                        print("step:", current_step, "accuracy:", sess.run(accuracy, feed_dict={
                            dropout_keep_prob: FLAGS.dropout_keep_prob}))

            print("accuracy: ", sess.run(accuracy, feed_dict={
                dropout_keep_prob: FLAGS.dropout_keep_prob}))
            save_path = saver.save(sess, ckpt_path)
            print("Model saved in file: %s" % save_path)

            # stop queue runner
            coord.request_stop()
            coord.join(threads)


def main(_):
    """
    main function 
    """
    # # copy data to run file
    # copy_data_path = os.path.join('copy_data', FLAGS.dataset)
    # # copy train data
    # if not tf.gfile.Exists(copy_data_path):
    #     tf.gfile.MakeDirs(copy_data_path)
    # for file_path in tf.gfile.Glob(os.path.join(FLAGS.buckets, FLAGS.dataset, "*")):
    #     tf.gfile.Copy(file_path, os.path.join(copy_data_path,
    #                                           os.path.basename(file_path)), overwrite=True)
    # # copy google vector bin file
    # for file_path in tf.gfile.Glob(os.path.join(FLAGS.buckets, '*.bin')):
    #     tf.gfile.Copy(file_path, os.path.join('copy_data',
    #                                           os.path.basename(file_path)), overwrite=True)

    # FLAGS.buckets = './cope_data/'
    train()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Parameters
    # 获得buckets路径
    parser.add_argument('--buckets', type=str,
                        default='../../../data/data_by_ocean', help='input data path')
    # 获得数据库
    parser.add_argument('--dataset', type=str, default='eclipse', help='dataset')
    # 获得checkpoint路径
    parser.add_argument('--checkpointDir', type=str,
                        default='checkpoint_dir/', help='output model path')
    # 获得logs地址
    parser.add_argument('--summaryDir', type=str, default='logs/', help='output model path')

    # Model Hyperparameter
    parser.add_argument("--filter_sizes", type=str, default='3,4,5',
                        help="Comma-separated filter sizes")
    parser.add_argument("--num_filters", type=int, default=100,
                        help="Number of filters per filter size")
    parser.add_argument("--dropout_keep_prob", type=float,
                        default=0.5, help="Dropout keep probability")
    parser.add_argument("--l2_reg_lambda", type=float, default=0., help="L2 regularization lambda")
    parser.add_argument("--init_learning_rate", type=float, default=1e-4, help="learning rate")
    parser.add_argument("--decay_rate", type=float, default=0.96, help="decay rate")

    # # Training parameters
    parser.add_argument("--num_classes", type=int, default=2473, help="number of classes")
    parser.add_argument("--vocabulary_size", type=int, default=312684,
                        help="vocabulary size of data")
    parser.add_argument("--embedding_dim", type=int, default=300,
                        help="Dimensionality of character embedding")
    parser.add_argument("--batch_size", type=int, default=100, help="Batch Size")
    parser.add_argument("--num_train", type=int, default=179964, help="Number of train data")
    parser.add_argument("--num_epochs", type=int, default=200, help="Number of training epochs")
    parser.add_argument("--evaluate_every", type=int, default=100,
                        help="Evaluate model on dev set after this many steps")
    parser.add_argument("--checkpoint_every", type=int, default=100,
                        help="Save model after this many steps")
    parser.add_argument("--num_checkpoints", type=int, default=500,
                        help="Number of checkpoints to store")
    parser.add_argument("--top_k", type=int, default=1, help="evaluation top k")
    parser.add_argument("--embedding_type", type=str, default="non_static",
                        help="rand, static,none_static, multiple_channels")

    # # Misc Parameters
    parser.add_argument("--allow_soft_placement", type=bool, default=True,
                        help="Allow device soft device placement")
    parser.add_argument("--log_device_placement", type=bool, default=False,
                        help="Log placement of ops on devices")

    FLAGS, _ = parser.parse_known_args()

    if not tf.gfile.Exists(FLAGS.checkpointDir):
        tf.gfile.MakeDirs(FLAGS.checkpointDir)
    # if not tf.gfile.Exists(FLAGS.buckets):
    #     tf.gfile.MakeDirs(FLAGS.buckets)
    if not tf.gfile.Exists(FLAGS.summaryDir):
        tf.gfile.MakeDirs(FLAGS.summaryDir)

    tf.app.run(main=main)
