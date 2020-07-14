import os
import sys
import tensorflow as tf
from tensorflow import data
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, Conv2D, GlobalAveragePooling2D
from tensorflow.keras.callbacks import LearningRateScheduler, CSVLogger
from functools import partial

import numpy as np
from time import time

np.random.seed(1000)

jobid = sys.argv[1]
# Directory of the images, will need to replace this as necessary
trainDirectory = '/tmp/' + jobid + '/ramdisk/imagenet12/images/train/'
valDirectory = '/tmp/' + jobid + '/ramdisk/imagenet12/images/sortedVal/'

# Get a list of directories where their indices act as labels
cats = tf.convert_to_tensor(os.listdir(trainDirectory))

# Mean of Imagenet channels
mean = tf.stack([tf.zeros([224, 224])+103.939,
                 tf.zeros([224, 224])+116.779,
                 tf.zeros([224, 224])+123.68], axis=2)


# Function to take each file and get the image and their label
def process_train_image(path):
    # Label is the directory
    label = tf.where(cats == tf.strings.split(path, '/')[-2])[0]
    label = tf.one_hot(label[0], cats.shape[0])

    # Load image
    img = tf.io.read_file(path)
    img = tf.image.decode_jpeg(img, channels=3)

    # Scale randomly and crop image as needed
    shape = tf.shape(img)
    dim1 = tf.cast(shape[0], dtype='float32')
    dim2 = tf.cast(shape[1], dtype='float32')
    scale = tf.random.uniform([], minval=256, maxval=512, dtype='float32')

    if dim1 < scale or dim2 < scale:
        if dim1 < dim2:
            newDim1 = dim2/dim1*scale
            newDim1 = tf.math.round(newDim1)
            img = tf.image.resize(img, [newDim1, scale])
        else:
            newDim2 = dim1/dim2*scale
            newDim2 = tf.math.round(newDim2)
            img = tf.image.resize(img, [scale, newDim2])
    else:
        img = tf.image.convert_image_dtype(img, tf.float32)

    # Random horizontal flip
    img = tf.image.random_flip_left_right(img)

    # Crop to centre (note that this never pads)
    img = tf.image.resize_with_crop_or_pad(img, 224, 224)

    # Roughly approximate RGB shift (need to actually do PCA on the entire dataset)
    img = tf.image.random_hue(img, 0.1)

    # Zero mean
    img -= mean

    return img, label


# Processor for validation images
def process_val_image(path):
    # Label is the directory
    label = tf.where(cats == tf.strings.split(path, '/')[-2])[0]
    label = tf.one_hot(label[0], cats.shape[0])

    # Load image
    img = tf.io.read_file(path)
    img = tf.image.decode_jpeg(img, channels=3)

    # Scale randomly and crop image as needed
    shape = tf.shape(img)
    dim1 = tf.cast(shape[0], dtype='float32')
    dim2 = tf.cast(shape[1], dtype='float32')
    scale = 224

    if dim1 < scale or dim2 < scale:
        if dim1 < dim2:
            newDim1 = dim2/dim1*scale
            newDim1 = tf.math.round(newDim1)
            img = tf.image.resize(img, [newDim1, scale])
        else:
            newDim2 = dim1/dim2*scale
            newDim2 = tf.math.round(newDim2)
            img = tf.image.resize(img, [scale, newDim2])
    else:
        img = tf.image.convert_image_dtype(img, tf.float32)

    # Crop to centre (note that this never pads)
    img = tf.image.resize_with_crop_or_pad(img, 224, 224)

    # Zero mean
    img -= mean

    return img, label


# Create datasets
trainData = data.Dataset.list_files(trainDirectory + '*/*.JPEG')\
    .prefetch(tf.data.experimental.AUTOTUNE)\
    .map(process_train_image, num_parallel_calls=tf.data.experimental.AUTOTUNE)\
    .batch(128)

valData = data.Dataset.list_files(valDirectory + '*/*.JPEG')\
    .prefetch(tf.data.experimental.AUTOTUNE)\
    .map(process_val_image, num_parallel_calls=tf.data.experimental.AUTOTUNE)\
    .batch(256)


model = Sequential()

# Define initializers
glorotInit = tf.keras.initializers.glorot_uniform()
truncNormInit = tf.keras.initializers.TruncatedNormal(0, 0.005)
constantInit = tf.keras.initializers.Constant(0.1)

# Define regularizers
l2Reg = tf.keras.regularizers.l2(1e-5)

# SGD optimizer
sgd = tf.keras.optimizers.SGD(lr=0.01, momentum=0.9, nesterov=False)

# 1st Convolutional Layer
model.add(Conv2D(filters=96, input_shape=(224, 224, 3), kernel_size=(11, 1), strides=(4, 4),
                 padding='same', name='Input', kernel_initializer=glorotInit,
                 kernel_regularizer=l2Reg, bias_initializer=constantInit))

# .2 dropout for inputs, .5 otherwise
model.add(Dropout(0.2))

# 2nd Convolutional Layer
model.add(Conv2D(filters=96, kernel_size=(1, 1), strides=(1, 1), padding='same', activation='relu',
                 kernel_initializer=glorotInit, kernel_regularizer=l2Reg, bias_initializer=constantInit))

# 3rd Convolutional Layer
model.add(Conv2D(filters=96, kernel_size=(3, 3), strides=(2, 2), padding='same', activation='relu',
                 kernel_initializer=glorotInit, kernel_regularizer=l2Reg, bias_initializer=constantInit))

model.add(Dropout(0.5))

# 4th Convolutional Layer
model.add(Conv2D(filters=256, kernel_size=(5, 5), strides=(1, 1), padding='same', activation='relu',
                 kernel_initializer=glorotInit, kernel_regularizer=l2Reg, bias_initializer=constantInit))

# 5th Convolutional Layer
model.add(Conv2D(filters=256, kernel_size=(1, 1), strides=(1, 1), padding='same', activation='relu',
                 kernel_initializer=glorotInit, kernel_regularizer=l2Reg, bias_initializer=constantInit))

# 6th Convolutional Layer
model.add(Conv2D(filters=256, kernel_size=(3, 3), strides=(2, 2), padding='same', activation='relu',
                 kernel_initializer=glorotInit, kernel_regularizer=l2Reg, bias_initializer=constantInit))

model.add(Dropout(0.5))

# 7th Convolutional Layer
model.add(Conv2D(filters=384, kernel_size=(3, 3), strides=(1, 1), padding='same', activation='relu',
                 kernel_initializer=glorotInit, kernel_regularizer=l2Reg, bias_initializer=constantInit))

# 8th Convolutional Layer
model.add(Conv2D(filters=384, kernel_size=(1, 1), strides=(1, 1), padding='same', activation='relu',
                 kernel_initializer=glorotInit, kernel_regularizer=l2Reg, bias_initializer=constantInit))

# 9th Convolutional Layer
model.add(Conv2D(filters=384, kernel_size=(3, 3), strides=(2, 2), padding='same', activation='relu',
                 kernel_initializer=glorotInit, kernel_regularizer=l2Reg, bias_initializer=constantInit))

model.add(Dropout(0.5))

# 10th Convolutional Layer
model.add(Conv2D(filters=1024, kernel_size=(3, 3), strides=(1, 1), padding='same', activation='relu',
                 kernel_initializer=glorotInit, kernel_regularizer=l2Reg, bias_initializer=constantInit))

# 11th Convolutional Layer
model.add(Conv2D(filters=1024, kernel_size=(1, 1), strides=(1, 1), padding='same', activation='relu',
                 kernel_initializer=glorotInit, kernel_regularizer=l2Reg, bias_initializer=constantInit))

# 12th Convolutional Layer
model.add(Conv2D(filters=1000, kernel_size=(1, 1), strides=(1, 1), padding='same', activation='relu',
                 kernel_initializer=glorotInit, kernel_regularizer=l2Reg, bias_initializer=constantInit))

# Global average pooling
model.add(GlobalAveragePooling2D())

# Output Layer
model.add(Dense(1000, activation='softmax', name='Classification'))

model.summary()


# Learning rate scheduler
#def scheduler(epoch):
#    if epoch < 5:
#        return 0.001
#    else:
#        return 0.00001


# lrcallback = LearningRateScheduler(scheduler)

# Callback to save model at beginning of every epoch in case of failure
model_path = "model_data" + "/" + jobid + "/"

if not os.path.exists(model_path):
    os.makedirs(model_path)

class SaveModelStateCallback(tf.keras.callbacks.Callback):
    def on_train_begin(self, logs={}):
        self.times = []

    def on_epoch_begin(self, epoch, logs=None):
        self.model.save(model_path + "checkpoint{}".format(epoch))
        self.epoch_time_start = time()

    def on_epoch_end(self, batch, logs={}):
        self.times.append(time() - self.epoch_time_start)

# Saving history in case of failure
csv_logger = CSVLogger(model_path + jobid + "_model_history_log.csv", append=True)

model_state = SaveModelStateCallback()

# Start from checkpoint weights, if it exists
# old_jobid = 12123214
# old_chkpt_num = 4
# model.load_weights("model_data" + "/" + old_jobid + "/checkpoint{}".format(old_chkpt_num)

# Get top 5 accuracy data instead of just accuracy
top5_acc = partial(tf.keras.metrics.top_k_categorical_accuracy, k=5)

top5_acc.__name__ = 'top5_acc'


# Compile the model
model.compile(loss=tf.keras.losses.categorical_crossentropy, optimizer='adam', metrics=[top5_acc])

start = time()

history = model.fit(trainData, epochs=2, batch_size=128, verbose=1,
                    validation_data=valData, callbacks=[model_state,csv_logger])
end = time()

epoch_times = model_state.times

np.savetxt(model_path + jobid + 'epoch_training_times.csv', epoch_times, delimiter=',')

print("Training time is: " + str(end - start))
score = model.evaluate(valData, batch_size=128)