#!/usr/bin/env python
# -*- coding: utf-8 -*-
# _Author_: xiaofeng
# Date: 2018-04-01 12:12:42
# Last Modified by: xiaofeng
# Last Modified time: 2018-04-01 12:12:42

from PIL import Image
import tensorflow as tf
import tflib
import tflib.ops
import tflib.network
from tqdm import tqdm
import numpy as np
import data_loaders
import time
import os
import shutil
import datetime
import config_char_formula as cfg
slim = tf.contrib.slim

BATCH_SIZE = 32
EMB_DIM = 80
ENC_DIM = 256
DEC_DIM = ENC_DIM * 2
NUM_FEATS_START = 64
D = NUM_FEATS_START * 8
V = cfg.V_OUT  # vocab size
NB_EPOCHS = 100000
H = 20
W = 50
PRECEPTION = 0.6
THREAD = 13
LEARNING_DECAY = 20000
IMG_PATH = cfg.IMG_DATA_PATH

ckpt_path = cfg.CHECKPOINT_PATH
summary_path = cfg.SUMMARY_PATH
if not os.path.exists(ckpt_path):
    os.makedirs(ckpt_path)


def exist_or_not(path):
    if not os.path.exists(path):
        os.makedirs(path)


exist_or_not(summary_path)

with open('config.txt', 'w+') as f:
    cfg_dict = cfg.__dict__
    for key in sorted(cfg_dict.keys()):
        if key[0].isupper():
            cfg_str = '{}: {}\n'.format(key, cfg_dict[key])
            f.write(cfg_str)
    f.close()


X = tf.placeholder(shape=(None, None, None, None), dtype=tf.float32)  # 原文中的X占位符
mask = tf.placeholder(shape=(None, None), dtype=tf.int32)
seqs = tf.placeholder(shape=(None, None), dtype=tf.int32)
learn_rate = tf.placeholder(tf.float32)
input_seqs = seqs[:, :-1]
target_seqs = seqs[:, 1:]
ctx = tflib.network.im2latex_cnn(X, NUM_FEATS_START, True)  # 原始repo中卷积方式
# ctx = tflib.network.vgg16(X)  # 使用vgg16的卷积方式

# 进行编码
emb_seqs = tflib.ops.Embedding('Embedding', V, EMB_DIM, input_seqs)
out, state = tflib.ops.im2latexAttention('AttLSTM', emb_seqs, ctx, EMB_DIM,
                                         ENC_DIM, DEC_DIM, D, H, W)
logits = tflib.ops.Linear('MLP.1', out, DEC_DIM, V)

predictions = tf.argmax(tf.nn.softmax(logits[:, -1]), axis=1)
loss = tf.reshape(
    tf.nn.sparse_softmax_cross_entropy_with_logits(
        logits=tf.reshape(logits, [-1, V]),
        labels=tf.reshape(seqs[:, 1:], [-1])), [tf.shape(X)[0], -1])
# add paragraph ⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️⬇️
output = tf.reshape(logits, [-1, V])
output_index = tf.to_int32(tf.argmax(output, 1))
true_labels = tf.reshape(seqs[:, 1:], [-1])
correct_prediction = tf.equal(output_index, true_labels)
accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))
# ⬆️⬆️⬆️⬆️⬆️⬆️⬆️⬆️⬆️⬆️⬆️⬆️⬆️⬆️⬆️⬆️⬆️
mask_mult = tf.to_float(mask[:, 1:])
loss_total = tf.reduce_sum(loss * mask_mult) / tf.reduce_sum(mask_mult)

optimizer = tf.train.GradientDescentOptimizer(learn_rate)
# optimizer = tf.train.MomentumOptimizer(learn_rate, 0.9)
gvs = optimizer.compute_gradients(loss_total)
capped_gvs = [(tf.clip_by_norm(grad, 5.), var) for grad, var in gvs]
train_step = optimizer.apply_gradients(capped_gvs)

# summary

tf.summary.scalar('model_loss', loss_total)
# tf.summary.scalar('model_prediction', predictions)
tf.summary.scalar('model_accuracy', accuracy)
tf.summary.histogram('model_loss_his', loss_total)
tf.summary.histogram('model_acc_his', accuracy)
gradient_norms = [tf.norm(grad) for grad, var in gvs]
tf.summary.histogram('gradient_norm', gradient_norms)
tf.summary.scalar('max_gradient_norm', tf.reduce_max(gradient_norms))
merged = tf.summary.merge_all()


# function to predict the latex
def score(set='valididate', batch_size=32):
    score_itr = data_loaders.data_iterator(set, batch_size)
    losses = []
    for score_imgs, score_seqs, score_mask in score_itr:
        _loss = sess.run(
            loss_total,
            feed_dict={
                X: score_imgs,
                seqs: score_seqs,
                mask: score_mask
            })
        losses.append(_loss)
    set_loss = np.mean(losses)

    perp = np.mean(list(map(lambda x: np.power(np.e, x), losses)))
    return set_loss, perp


def predict(set='test', batch_size=1, visualize=True):
    if visualize:
        assert (batch_size == 1), "Batch size should be 1 for visualize mode"
    import random
    # f = np.load('train_list_buckets.npy').tolist()
    f = np.load(set+'_buckets.npy').tolist()
    random_key = random.choice(f.keys())
    #random_key = (160,40)
    f = f[random_key]
    imgs = []
    print("Image shape: ", random_key)
    while len(imgs) != batch_size:
        start = np.random.randint(0, len(f), 1)[0]
        if os.path.exists('./images_processed/'+f[start][0]):
            imgs.append(
                np.asarray(Image.open('./images_processed/' + f[start][0]).convert('YCbCr'))[:, :, 0]
                [:, :, None])

    # imgs = np.asarray(imgs, dtype=np.float32).transpose(0, 3, 1, 2)
    inp_seqs = np.zeros((batch_size, 160)).astype('int32')
    print(imgs.shape)
    inp_seqs[:, 0] = np.load(cfg.PROPERTIES).tolist()['char_to_idx']['#START']
    tflib.ops.ctx_vector = []

    l_size = random_key[0]*2
    r_size = random_key[1]*2
    inp_image = Image.fromarray(imgs[0][0]).resize((l_size, r_size))
    l = int(np.ceil(random_key[1]/8.))
    r = int(np.ceil(random_key[0]/8.))
    properties = np.load(cfg.PROPERTIES).tolist()

    def idx_to_chars(Y): return ' '.join(map(lambda x: properties['idx_to_char'][x], Y))

    for i in range(1, 160):
        inp_seqs[:, i] = sess.run(predictions, feed_dict={X: imgs, input_seqs: inp_seqs[:, :i]})
        # print i,inp_seqs[:,i]
        if visualize == True:
            att = sorted(
                list(enumerate(tflib.ops.ctx_vector[-1].flatten())),
                key=lambda tup: tup[1],
                reverse=True)
            idxs, att = zip(*att)
            j = 1
            while sum(att[:j]) < 0.9:
                j += 1
            positions = idxs[:j]
            print("Attention weights: ", att[:j])
            positions = [(pos/r, pos % r) for pos in positions]
            outarray = np.ones((l, r))*255.
            for loc in positions:
                outarray[loc] = 0.
            out_image = Image.fromarray(outarray).resize((l_size, r_size), Image.NEAREST)
            print("Latex sequence: ", idx_to_chars(inp_seqs[0, :i]))
            outp = Image.blend(inp_image.convert('RGBA'), out_image.convert('RGBA'), 0.5)
            outp.show(title=properties['idx_to_char'][inp_seqs[0, i]])
            # raw_input()
            time.sleep(3)
            os.system('pkill display')

    np.save('pred_imgs', imgs)
    np.save('pred_latex', inp_seqs)
    print("Saved npy files! Use Predict.ipynb to view results")
    return inp_seqs


# init = tf.global_variables_initializer()
init = tf.group(tf.global_variables_initializer(),
                tf.local_variables_initializer())
config = tf.ConfigProto(intra_op_parallelism_threads=THREAD)
# config.gpu_options.per_process_gpu_memory_fraction = PRECEPTION
sess = tf.Session(config=config)
sess.run(init)
# restore the weights
saver2 = tf.train.Saver(max_to_keep=3, keep_checkpoint_every_n_hours=0.5)
saver2_path = os.path.join(ckpt_path, 'weights_best.ckpt')

file_list = os.listdir(ckpt_path)
if file_list:
    for i in file_list:
        if i == 'checkpoint':
            print('Restore the weight files form:', ckpt_path)
            saver2.restore(sess, tf.train.latest_checkpoint(ckpt_path))
suammry_writer = tf.summary.FileWriter(
    summary_path, flush_secs=60, graph=sess.graph)

coord = tf.train.Coordinator()
thread = tf.train.start_queue_runners(sess=sess, coord=coord)

losses = []
times = []
print("Compiled Train function!")
# Test is train func runs
i = 0
iter = 0
best_perp = np.finfo(np.float32).max
property = np.load(cfg.PROPERTIES).tolist()


def idx_to_chars(Y):
    return ' '.join(map(lambda x: property['idx_to_char'][x], Y))


for i in range(NB_EPOCHS):
    print('best_perp', best_perp)
    costs = []
    times = []
    pred = []
    itr = data_loaders.data_iterator('train', BATCH_SIZE)
    for train_img, train_seq, train_mask in itr:
        iter += 1
        start = time.time()
        _, _loss, _loss_ori, _acc, _mask_mult, summary, _correct_prediction = sess.run(
            [train_step, loss_total, loss, accuracy, mask_mult, merged, correct_prediction],
            feed_dict={X: train_img, seqs: train_seq, mask: train_mask, learn_rate: 0.1})
        times.append(time.time() - start)
        costs.append(_loss)
        pred.append(_acc)
        suammry_writer.add_summary(summary)
        # print('_mask_mult:', tf.reduce_sum(_loss_ori * _mask_mult).eval(session=sess),
        #       tf.reduce_sum(_mask_mult).eval(session=sess))
        # print('acc:', tf.reduce_mean(tf.cast(_correct_prediction, tf.float32)).eval(session=sess))
        if iter % 100 == 0:
            print("Iter: %d (Epoch %d--%d)" % (iter, i + 1, NB_EPOCHS))
            print("\tMean cost: ", np.mean(costs), '===', _loss)
            print("\tMean prediction: ", np.mean(pred), '===', _acc)
            print("\tMean time: ", np.mean(times))
            print('\tSaveing summary to the path:', summary_path)
            print('\tSaveing model to the path:', saver2_path)

            suammry_writer.add_summary(summary, global_step=iter * i + iter)
            saver2.save(sess, saver2_path)

        if iter % 200 == 0:
            charlength = 200
            inp_seqs = np.zeros((1, charlength)).astype('int32')
            inp_seqs[:, 0] = property['char_to_idx']['<SPACE>']
            tflib.ops.ctx_vector = []
            true_char = idx_to_chars(train_seq[0].flatten().tolist())
            for i in range(1, charlength):
                feed = {X: [train_img[0]], input_seqs: inp_seqs[:, :i]}
                inp_seqs[:, i] = sess.run(predictions, feed_dict=feed)
            # formula_pred = idx_to_chars(inp_seqs.flatten().tolist()).split('#END')[0].split('#START')[-1]
            formula_pred = idx_to_chars(inp_seqs.flatten().tolist())
            print('\tTrue char is :', true_char)
            print('\tPredict char is:', formula_pred)
    print("\n\nEpoch %d Completed!" % (i + 1))
    print("\tMean train cost: ", np.mean(costs))
    print("\tMean train perplexity: ",
          np.mean(list(map(lambda x: np.power(np.e, x), costs))))
    print("\tMean time: ", np.mean(times))
    print('\n\n')
    print('processing the validate data...')
    val_loss, val_perp = score('validate', BATCH_SIZE)
    print("\tMean val cost: ", val_loss)
    print("\tMean val perplexity: ", val_perp)
    Info_out = datetime.datetime.now().strftime(
        '%Y-%m-%d %H:%M:%S') + '   ' + 'iter/epoch/epoch_nums-%d/%d/%d' % (
            iter, i,
            NB_EPOCHS) + '    ' + 'val cost/val perplexity:{}/{}'.format(
                val_loss, val_perp)
    with open(summary_path + 'val_loss.txt', 'a') as file:
        file.writelines(Info_out)
    file.close()
    if val_perp < best_perp:
        best_perp = val_perp
        saver2.save(sess, saver2_path)
        print("\tBest Perplexity Till Now! Saving state!")
coord.request_stop()
coord.join(thread)
