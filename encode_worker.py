# -*- coding: utf-8 -*-
# @Author  : ZHOUXU

import torch
import numpy as np
from PIL import Image
import cv2

from .encoder.models.tiny_vit import tiny_vit_21m_224,tiny_vit_5m_224,tiny_vit_11m_224
from .encoder.data import build_transform
from .encoder.config import get_config

class EncodeWorker:
    config = get_config()
    def __init__(self, checkpoint):
        def _pretrained_filter_fn(state_dict):
            state_dict = state_dict['model']
            # filter out attention_bias_idxs
            state_dict = {k: v for k, v in state_dict.items() if \
                          not k.endswith('attention_bias_idxs')}
            return state_dict

        self.transform = build_transform(is_train=False, config=self.config)
        #device = 'cuda'
        # tdevice = torch.device(device)
        tdevice = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = tiny_vit_5m_224(pretrained=False)

        if checkpoint is not None:
            with open(checkpoint, "rb") as f:
                state_dict = torch.load(f, map_location=tdevice)
                #state_dict = torch.load(f)
                state_dict = _pretrained_filter_fn(state_dict)
                self.model.load_state_dict(state_dict, strict=True)
                self.model.to(tdevice)
                self.model.eval()
        self.image = None

    def get_embedding(self,image=None):
        #print("Shape of expecting image:", np.array(image).shape)
        if image is not None:
            self.image = Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))

        if self.image is not None:
            #print("Shape of embedded image:",np.array(self.image).shape)
            batch = self.transform(self.image)[None]
            #print("Shape of embedded batch:",batch.shape)
            tdevice = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            batch = batch.to(tdevice)
            with torch.no_grad():
                embedding = self.model.forward_features(batch)
                embedding = embedding.cpu()
                #print("Shape of embbeding results:",embedding.shape)

            return embedding
        else:
            print("You must Set Image first")

    def get_embeddings_in_batch(self, input_images=None):
        '''
        计划：20230927
        希望一次对一批图片进行embedding，需要继续研究
        已完成：20230929
        注意：采用GPU，需要显式调用 batch.to(tdevice)，
        模型也需要显式调用self.model.to(tdevice)，仅仅在torch.load(f, map_location=tdevice)指定map_location并不起作用
        embbedding结果需要调用embeddings=embeddings.cpu()，否则后续计算有误
        '''
        # print_log("Shape of expecting image:", np.array(image).shape)
        img_tensors=[]
        if input_images is not None:
            #self.image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            for img in input_images:
                img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                img = self.transform(img)  # trans to C*W*H
                img_tensors.append(img)
            # trans to N*C*W*H
            #batch = self.transform(self.image)[None]
            batch = torch.tensor(np.array([item.detach().numpy() for item in img_tensors]))
            #print("Shape of embedded image:",batch.shape)
            # device="cuda"
            # tdevice = torch.device(device)
            tdevice = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            batch = batch.to(tdevice)

            with torch.no_grad():
                embeddings = self.model.forward_features(batch)
                #计算如果在gpu上进心，结果也在gpu上，在cpu上进一步使用结果时，必须转移到CPU上，否则若直接引用该变量，计算结果为0值
                embeddings=embeddings.cpu()
                #print("Shape of embbeding results:",embeddings.shape,embeddings[0])
            return embeddings
        else:
            print_log("You must Set Image first")

    def predict(self):
        batch = self.transform(self.image)[None]
        with torch.no_grad():
            logits = self.model(batch)

            # print top-5 classification names
            probs = torch.softmax(logits, -1)
            scores, inds = probs.topk(5, largest=True, sorted=True)
            print_log('=' * 30)
            for score, ind in zip(scores[0].numpy(), inds[0].numpy()):
                print_log(ind, score)

    def set_image(self,image):
        '''
        image:PIL formate image.cV2的需要转成PIL的
        '''
        self.image=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))


    def reset_image(self):
        self.image = None
        torch.cuda.empty_cache()


# def main():
#     fname = 'encoder/.figure/cat.jpg'
#     image = Image.open(fname)
#
#     print_log(fname)
#     checkpoint = "encoder/weights/tiny_vit_5m_22k_distill.pth"
#     encoder=EncodeWorker(checkpoint)
#     encoder.set_image(image)
#     embedding=encoder.get_embedding(image)
#     print_log(embedding.shape)
#     encoder.predict()
#
# main()