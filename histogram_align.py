import cv2
import numpy as np
def get_map(Hist):
    # 计算概率分布Pr
    sum_Hist = sum(Hist)
    Pr = Hist / sum_Hist
    # 计算累计概率Sk
    Sk = []
    temp_sum = 0
    for n in Pr:
        temp_sum = temp_sum + n
        Sk.append(temp_sum)
    Sk = np.array(Sk).squeeze()
    # 计算映射关系img_map
    img_map = []
    for m in range(256):
        temp_map = int(255 * Sk[m] + 0.5)
        img_map.append(temp_map)
    img_map = np.array(img_map)
    return img_map


def get_off_map(map_):  # 计算反向映射，寻找最小期望
    map_2 = list(map_)
    off_map = []
    temp_pre = 0  # 如果循环开始就找不到映射时，默认映射为0
    for n in range(256):
        try:
            temp1 = map_2.index(n)
            temp_pre = temp1
        except BaseException:
            temp1 = temp_pre  # 找不到映射关系时，近似取向前最近的有效映射值
        off_map.append(temp1)
    off_map = np.array(off_map)
    return off_map


def get_infer_map(infer_img):
    infer_Hist_b = cv2.calcHist([infer_img], [0], None, [256], [0, 255])
    infer_Hist_g = cv2.calcHist([infer_img], [1], None, [256], [0, 255])
    infer_Hist_r = cv2.calcHist([infer_img], [2], None, [256], [0, 255])
    infer_b_map = get_map(infer_Hist_b)
    infer_g_map = get_map(infer_Hist_g)
    infer_r_map = get_map(infer_Hist_r)
    infer_b_off_map = get_off_map(infer_b_map)
    infer_g_off_map = get_off_map(infer_g_map)
    infer_r_off_map = get_off_map(infer_r_map)
    return [infer_b_off_map, infer_g_off_map, infer_r_off_map]


def get_finalmap(org_map, infer_off_map):  # 计算原始图像到最终输出图像的映射关系
    org_map = list(org_map)
    infer_off_map = list(infer_off_map)
    final_map = []
    for n in range(256):
        temp1 = org_map[n]
        temp2 = infer_off_map[temp1]
        final_map.append(temp2)
    final_map = np.array(final_map)
    return final_map


def get_newimg(img_org, org2infer_maps):
    w, h, _ = img_org.shape
    b, g, r = cv2.split(img_org)
    for i in range(w):
        for j in range(h):
            temp1 = b[i, j]
            b[i, j] = org2infer_maps[0][temp1]
    for i in range(w):
        for j in range(h):
            temp1 = g[i, j]
            g[i, j] = org2infer_maps[1][temp1]
    for i in range(w):
        for j in range(h):
            temp1 = r[i, j]
            r[i, j] = org2infer_maps[2][temp1]
    newimg = cv2.merge([b, g, r])
    return newimg


def get_new_img(img_org, infer_map):
    org_Hist_b = cv2.calcHist([img_org], [0], None, [256], [0, 255])
    org_Hist_g = cv2.calcHist([img_org], [1], None, [256], [0, 255])
    org_Hist_r = cv2.calcHist([img_org], [2], None, [256], [0, 255])
    org_b_map = get_map(org_Hist_b)
    org_g_map = get_map(org_Hist_g)
    org_r_map = get_map(org_Hist_r)
    org2infer_map_b = get_finalmap(org_b_map, infer_map[0])
    org2infer_map_g = get_finalmap(org_g_map, infer_map[1])
    org2infer_map_r = get_finalmap(org_r_map, infer_map[2])
    return get_newimg(img_org, [org2infer_map_b, org2infer_map_g, org2infer_map_r])
