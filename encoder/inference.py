"""Model Inference."""
import torch
import numpy as np
from PIL import Image

from models.tiny_vit import tiny_vit_21m_224,tiny_vit_5m_224,tiny_vit_11m_224
from data import build_transform, imagenet_classnames
from config import get_config
config = get_config()

# Build model
def _pretrained_filter_fn(state_dict):
    state_dict = state_dict['model']
    # filter out attention_bias_idxs
    state_dict = {k: v for k, v in state_dict.items() if \
                  not k.endswith('attention_bias_idxs')}
    return state_dict

checkpoint="weights/tiny_vit_5m_22k_distill.pth"
model = tiny_vit_5m_224(pretrained=False)

with open(checkpoint, "rb") as f:
      state_dict = torch.load(f,map_location="cpu")

state_dict=_pretrained_filter_fn(state_dict)
model.load_state_dict(state_dict,strict=True)
model.eval()

# Load Image
fname = './.figure/cat.jpg'
image = Image.open(fname)
print_log(np.array(image).shape)
transform = build_transform(is_train=False, config=config)

# (1, 3, img_size, img_size)
batch = transform(image)[None]
print_log(batch.shape)

with torch.no_grad():
    logits = model(batch)
    embedding=model.forward_features(batch)
print_log(embedding.shape)

# print top-5 classification names
probs = torch.softmax(logits, -1)
scores, inds = probs.topk(5, largest=True, sorted=True)
print_log('=' * 30)
print_log(fname)
for score, ind in zip(scores[0].numpy(), inds[0].numpy()):
    print_log(ind,score)
    #print_log(f'{imagenet_classnames[ind]}: {score:.2f}')
