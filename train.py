# coding:utf-8
import os
import argparse
import time

import torch
import torch.nn.functional as F
from torch.autograd import Variable
from torch.utils.data import DataLoader
from fractions import Fraction

from util.MF_dataset import MF_dataset
from util.util import calculate_accuracy, DEVICE, channel_filename
from util.augmentation import RandomFlip, RandomCrop, RandomCropOut, RandomBrightness, RandomNoise
from model import MFNet, SegNet
from attack import MyAttack, get_attack

from tqdm import tqdm

# config
n_class   = 9
data_dir  = 'data/MF/'
model_dir = 'weights/'
augmentation_methods = [
    RandomFlip(prob=0.5),
    RandomCrop(crop_rate=0.1, prob=1.0), 
    # RandomCropOut(crop_rate=0.2, prob=1.0),
    # RandomBrightness(bright_range=0.15, prob=0.9),
    # RandomNoise(noise_range=5, prob=0.9),
]
lr_start  = 0.01
lr_decay  = 0.95


def train(epo, model, train_loader, optimizer, adv_train=False):
    lr_this_epo = lr_start * lr_decay**(epo-1)
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr_this_epo

    loss_avg = 0.
    acc_avg  = 0.
    start_t = t = time.time()
    
    model.train()
    for it, (images, labels, names) in enumerate(train_loader):
        images = Variable(images).cuda(args.gpu) 
        labels = Variable(labels).cuda(args.gpu)
        if args.gpu >= 0:
            images = images.cuda(args.gpu)
            labels = labels.cuda(args.gpu)
        
        if adv_train == True:
            model.eval()
            atk_train = get_attack(args, model)
            images = atk_train(images, labels)
            model.train()
            
        optimizer.zero_grad()
        logits = model(images)
        loss = F.cross_entropy(logits, labels)
        loss.backward()
        optimizer.step()

        acc = calculate_accuracy(logits, labels)
        loss_avg += float(loss)
        acc_avg  += float(acc)

        cur_t = time.time()
        if cur_t-t > 5:
            print('|- epo %s/%s. train iter %s/%s. %.2f img/sec loss: %.4f, acc: %.4f' \
                % (epo, args.epoch_max, it+1, train_loader.n_iter, (it+1)*args.batch_size/(cur_t-start_t), float(loss), float(acc)))
            t += 5

    content = '| epo:%s/%s lr:%.4f train_loss_avg:%.4f train_acc_avg:%.4f ' \
            % (epo, args.epoch_max, lr_this_epo, loss_avg/train_loader.n_iter, acc_avg/train_loader.n_iter)
    print(content)
    with open(log_file, 'a') as appender:
        appender.write(content)


def validation(epo, model, val_loader):
    loss_avg = 0.
    acc_avg  = 0.
    start_t = time.time()
    
    model.eval()
    with torch.no_grad():
        for it, (images, labels, names) in enumerate(val_loader):
            images = Variable(images)
            labels = Variable(labels)
            if args.gpu >= 0:
                images = images.cuda(args.gpu)
                labels = labels.cuda(args.gpu)

            logits = model(images)
            loss = F.cross_entropy(logits, labels)
            acc = calculate_accuracy(logits, labels)
            loss_avg += float(loss)
            acc_avg  += float(acc)

            cur_t = time.time()
            print('|- epo %s/%s. val iter %s/%s. %.2f img/sec loss: %.4f, acc: %.4f' \
                    % (epo, args.epoch_max, it+1, val_loader.n_iter, (it+1)*args.batch_size/(cur_t-start_t), float(loss), float(acc)))

    content = '| val_loss_avg:%.4f val_acc_avg:%.4f\n' \
            % (loss_avg/val_loader.n_iter, acc_avg/val_loader.n_iter)
    print(content)
    with open(log_file, 'a') as appender:
        appender.write(content)


def main():
    if args.model_name == 'SegNet':
        model = eval(args.model_name)(n_class=n_class, in_channels=args.channels)
    else:
        model = eval(args.model_name)(n_class=n_class)
        
    if args.gpu >= 0: model.cuda(args.gpu)
    optimizer = torch.optim.SGD(model.parameters(), lr=lr_start, momentum=0.9, weight_decay=0.0005) 

    if args.epoch_from > 1:
        print('| loading checkpoint file %s... ' % checkpoint_model_file, end='')
        model.load_state_dict(torch.load(checkpoint_model_file, map_location=DEVICE))
        optimizer.load_state_dict(torch.load(checkpoint_optim_file))
        print('done!')

    train_dataset = MF_dataset(data_dir, 'train', have_label=True, transform=augmentation_methods)
    val_dataset  = MF_dataset(data_dir, 'val', have_label=True)

    train_loader  = DataLoader(
        dataset     = train_dataset,
        batch_size  = args.batch_size,
        shuffle     = True,
        num_workers = args.num_workers,
        pin_memory  = True,
        drop_last   = True
    )
    val_loader  = DataLoader(
        dataset     = val_dataset,
        batch_size  = args.batch_size,
        shuffle     = False,
        num_workers = args.num_workers,
        pin_memory  = True,
        drop_last   = False
    )
    train_loader.n_iter = len(train_loader)
    val_loader.n_iter   = len(val_loader)

    for epo in tqdm(range(args.epoch_from, args.epoch_max+1)):
        print('\n| epo #%s begin...' % epo)

        train(epo, model, train_loader, optimizer, adv_train=args.adv_train)
        validation(epo, model, val_loader)

        # save check point model
        print('| saving check point model file... ', end='')
        torch.save(model.state_dict(), checkpoint_model_file)
        torch.save(optimizer.state_dict(), checkpoint_optim_file)
        print('done!')

    os.rename(checkpoint_model_file, final_model_file)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train MFNet with pytorch')
    parser.add_argument('--model_name',  '-M',  type=str, default='MFNet')
    parser.add_argument('--batch_size',  '-B',  type=int, default=8)
    parser.add_argument('--epoch_max' ,  '-E',  type=int, default=100)
    parser.add_argument('--epoch_from',  '-EF', type=int, default=1)
    parser.add_argument('--gpu',         '-G',  type=int, default=0)
    parser.add_argument('--num_workers', '-j',  type=int, default=0)
    parser.add_argument('--channels',    '-c',  type=int, default=4)
    
    parser.add_argument('--adv_train',              action='store_true')
    parser.add_argument('--method',                 type=str,   default='PGD')
    parser.add_argument('--eps',                    type=Fraction, default=Fraction(8, 255))
    parser.add_argument('--alpha',                  type=Fraction, default=Fraction(1, 255))
    parser.add_argument('--steps',                  type=int,   default=10)
    parser.add_argument('--atk_channel', '-atkc',   type=int, default=4)
    args = parser.parse_args()

    model_dir = os.path.join(model_dir, args.model_name)
    os.makedirs(model_dir, exist_ok=True)
    tmp_model, tmp_optim, final_model, log_name = channel_filename(args.channels, adv_train=args.adv_train)
    checkpoint_model_file = os.path.join(model_dir, tmp_model)
    checkpoint_optim_file = os.path.join(model_dir, tmp_optim)
    final_model_file      = os.path.join(model_dir, final_model)
    log_file              = os.path.join(model_dir, log_name)

    print('| training %s on GPU #%d with pytorch' % (args.model_name, args.gpu))
    print('| from epoch %d / %s' % (args.epoch_from, args.epoch_max))
    print('| model will be saved in: %s' % model_dir)

    main()
