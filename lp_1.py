import numpy as np
import tensorflow as tf
from sklearn.preprocessing import normalize
from math import acos, pi
import sys
np.random.seed(13)

if len(sys.argv) == 2:
    STOP = int(sys.argv[1])
elif len(sys.argv) == 1:
    STOP = 50000  # i.e. no number of words limit
else:
    sys.exit('Usage: lp_1.py [word limit]')

class Model:
    def __init__(self, n_labeled, n_unlabeled, n_classes):
        self._t_uu = t_uu = tf.placeholder(tf.float32, shape=[n_unlabeled, n_unlabeled])
        self._t_ul = t_ul = tf.placeholder(tf.float32, shape=[n_unlabeled, n_labeled])
        self._y_l = y_l = tf.placeholder(tf.float32, shape=[n_labeled, n_classes])

        self._w = w = tf.placeholder(tf.float32, shape=[])
        self._b = b = tf.placeholder(tf.float32, shape=[])

        tuu = tf.sigmoid(w * t_uu + b)
        tul = tf.sigmoid(w * t_ul + b)

        # column normalization
        tuu_col_norms = tf.norm(tuu, ord=1, axis=0)
        tul_col_norms = tf.norm(tul, ord=1, axis=0)
        tuu /= tuu_col_norms
        tul /= tul_col_norms

        # row normalization
        tuu_row_norms = tf.norm(tuu, ord=1, axis=1)
        tul_row_norms = tf.norm(tul, ord=1, axis=1)
        tuu /= tf.reshape(tuu_row_norms, [n_unlabeled, 1])
        tul /= tf.reshape(tul_row_norms, [n_unlabeled, 1])

        I = tf.eye(n_unlabeled, dtype=tf.float32)
        inv = tf.matrix_solve_ls((I - tuu), I, l2_regularizer=0.01)

        y_u = tf.matmul(tf.matmul(inv, tul), y_l)

        y = tf.concat([y_u, y_l], 0)
        self._y = y = tf.clip_by_value(y, 1e-15, float("inf"))


    @property
    def t_uu(self):
        return self._t_uu

    @property
    def t_ul(self):
        return self._t_ul

    @property
    def y_l(self):
        return self._y_l

    @property
    def y(self):
        return self._y

    @property
    def w(self):
        return self._w

    @property
    def b(self):
        return self._b


def read_emo_lemma(aline):
    """
    Splits a line into lemma l, emotion e, and l(e).
    l(e) := 1 if lemma l has emotion e according to the lexicon
    l(e) := 0 otherwise
    """
    split = aline.split()
    return split[0], split[1], int(split[2])



NUM_EMOTIONS = 6
NDIMS = 300

_embeddings = []
word2idx = {}
line_idx = 0
with open('resources/emotion_specific/bilstm_300d.txt', 'r', encoding='UTF-8') as f:
    next(f)  # skip header

    for line in f:
        if line_idx >= STOP:
            break

        values = line.split()

        # probably an error occurred during tokenization
        if len(values) != NDIMS + 1:
            continue

        word = values[0]
        coefs = np.asarray(values[1:], dtype='float32')

        # skip all-zeros vectors
        if not coefs.any():
            continue

        # only one vector for each word
        try:
            word2idx[word]
        except:
            _embeddings.append(coefs)
            word2idx[word] = line_idx
            line_idx += 1

n = line_idx
print('Found', n, 'word vectors.')

embeddings = np.asarray(_embeddings, dtype='float32')
embeddings = normalize(embeddings, axis=1, norm='l2', copy=False)

print('Build distance matrix.')
t = np.empty((n, n), dtype='float32')

log_count = 0
for j in word2idx.values():
    for k in word2idx.values():
        t[j, k] = embeddings[j] @ embeddings[k]

    log_count += 1
    if log_count % 1000 == 0:
        print(log_count, "/", n, sep="")

y_l = np.empty(shape=(14182, NUM_EMOTIONS), dtype='float32')
lexeme2index = dict()
with open('resources/data/emolex.txt', 'r') as f:
    emo_idx = 0  # anger: 0, disgust: 1, fear: 2, joy: 3, sadness: 4, surprise: 6
    i = 0
    for l in f:
        lemma, emotion, has_emotion = read_emo_lemma(l)
        if emotion == 'anger':  # i.e. if lemma not in lexicon.keys()
            lexeme2index[lemma] = i
        if emotion in ['positive', 'negative', 'anticipation', 'trust']:
            continue
        y_l[i][emo_idx] = has_emotion
        if emo_idx < NUM_EMOTIONS - 1:
            emo_idx += 1
        else:
            # reset index - next line contains a new lemma
            emo_idx = 0
            i += 1

print('Initialize label distribution matrix.')
y = np.random.random((n, NUM_EMOTIONS))

labeled_indices = []
for word, idx in lexeme2index.items():
    try:
        # if word in corpus
        idx_T = word2idx[word]  # get index of word in T
        y[idx_T] = y_l[idx]  # set values of labeled word
        labeled_indices.append(idx_T)
    except KeyError:
        continue

# turn multi-labels into prob distribution
y = normalize(y, axis=1, norm='l1', copy=False)

labeled_indices.sort()
l = labeled_indices
u = np.setdiff1d(np.asarray(list(word2idx.values()), dtype='int32'), l)

new_order = np.append(u, l)
t[:, :] = t[new_order][:, new_order]
y[:] = y[new_order]

T_uu = t[:len(u), :len(u)]
T_ul = t[:len(u), len(u):]
Y_l = y[len(u):]

i2i = np.zeros_like(new_order, dtype='int32')
for new, old in enumerate(new_order):
    i2i[old] = new

word2idx = {w: i2i[old] for w, old in word2idx.items()}

print('Tensorflow.')
sess = tf.Session()

with tf.variable_scope("model", reuse=False):
    model = Model(len(l), len(u), NUM_EMOTIONS)

sess.run(tf.global_variables_initializer())

Y = sess.run([model.y],
             {model.t_uu: T_uu, model.t_ul: T_ul, model.y_l: Y_l, model.w: -0.00109, model.b: 0.90099})

with open('y_1_5000-1000-3.txt', 'w', encoding='utf-8') as f:
    for w, i in word2idx.items():
        print(w, str(y[i]).replace('\n   ', '   ').replace('[', '').replace(']', ''), file=f)

sess.close()
