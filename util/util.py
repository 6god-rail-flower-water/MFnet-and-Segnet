# coding:utf-8
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

DEVICE = {'cpu':'cuda:0'}


def calculate_accuracy(logits, labels):
    # inputs should be torch.tensor
    predictions = logits.argmax(1)
    no_count = (labels==-1).sum()
    count = ((predictions==labels)*(labels!=-1)).sum()
    acc = count.float() / (labels.numel()-no_count).float()
    return acc


def calculate_result(cf):
    n_class = cf.shape[0]
    conf = np.zeros((n_class,n_class))
    IoU = np.zeros(n_class)
    conf[:,0] = cf[:,0]/cf[:,0].sum()
    for cid in range(1,n_class):
        if cf[:,cid].sum() > 0:
            conf[:,cid] = cf[:,cid]/cf[:,cid].sum()
            IoU[cid]  = cf[cid,cid]/(cf[cid,1:].sum()+cf[1:,cid].sum()-cf[cid,cid])
    overall_acc = np.diag(cf[1:,1:]).sum()/cf[1:,:].sum()
    acc = np.diag(conf)

    return overall_acc, acc, IoU


# for visualization
def get_palette():
    unlabelled = [0,0,0]
    car        = [64,0,128]
    person     = [64,64,0]
    bike       = [0,128,192]
    curve      = [0,0,192]
    car_stop   = [128,128,0]
    guardrail  = [64,64,128]
    color_cone = [192,128,128]
    bump       = [192,64,0]
    palette    = np.array([unlabelled,car, person, bike, curve, car_stop, guardrail, color_cone, bump])
    return palette


def visualize(names, predictions):
    palette = get_palette()

    for (i, pred) in enumerate(predictions):
        pred = predictions[i].cpu().numpy()
        img = np.zeros((pred.shape[0], pred.shape[1], 3), dtype=np.uint8)
        for cid in range(1, int(predictions.max())):
            img[pred == cid] = palette[cid]

        img = Image.fromarray(np.uint8(img))
        img.save(names[i].replace('.png', '_pred.png'))
        
def get_visual_image(pred):
    palette = get_palette()

    Pred = pred.to('cpu').squeeze(0).numpy()
    img = np.zeros((Pred.shape[0], Pred.shape[1], 3), dtype=np.uint8)
    for cid in range(1, int(pred.max())):
        img[Pred == cid] = palette[cid]
    #img = Image.fromarray(np.uint8(img))
    return img


def visual_and_plot(images, pred, pred_atk):
    images = images[:,:3].to('cpu').squeeze(0).permute(1, 2, 0).numpy()
    img = get_visual_image(pred)
    img_atk = get_visual_image(pred_atk)

    fig, ax = plt.subplots(1, 3, figsize=(15, 5))
    ax[0].imshow(images)
    ax[0].set_title('Original Image')
    ax[1].imshow(img)
    ax[1].set_title('Original Prediction')
    ax[2].imshow(img_atk)
    ax[2].set_title('Adversarial Prediction')
    
    plt.show()


def channel_filename(channel, adv_train=False):
    if adv_train == False:
        tmp_model_template = 'tmp_{0}.pth'
        tmp_optim_template = 'tmp_{0}.optim'
        final_model_template = 'final_{0}.pth'
        log_template = 'log_{0}.txt'
    else:
        tmp_model_template = 'tmp_{0}_adv.pth'
        tmp_optim_template = 'tmp_{0}_adv.optim'
        final_model_template = 'final_{0}_adv.pth'
        log_template = 'log_{0}_adv.txt'
    
    tmp_model = tmp_model_template.format(channel)
    tmp_optim = tmp_optim_template.format(channel)
    final_model = final_model_template.format(channel)
    log_file = log_template.format(channel)
    
    return tmp_model, tmp_optim, final_model, log_file