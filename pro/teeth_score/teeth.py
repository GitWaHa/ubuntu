import cv2
import numpy as np
import copy
import os

from unet_extract import *

TEETH_IMAGE_SET_ROW = 480
TEETH_IMAGE_SET_COL = 480


class Img_info:
    def __init__(self):
        self.patient_name = 0
        self.operation_time = 0
        self.operation_name = 0
        self.doctor_name = 0
        self.img_type = 0
        self.pro_path = 0

    def get_info(self, img_name, pro_path):
        img_name_str = img_name.split("-")
        self.patient_name = img_name_str[0]
        self.operation_time = img_name_str[1]
        self.operation_name = img_name_str[2]

        doctor_name_str = img_name_str[3].split(".")
        self.doctor_name = doctor_name_str[0]
        self.img_type = doctor_name_str[1]
        self.pro_path = pro_path

    def print_info(self):
        print("患者姓名：", self.patient_name)
        print("手术时间：", self.operation_time)
        print("手术名称：", self.operation_name)
        print("医生姓名：", self.doctor_name)
        print("图片格式：", self.img_type)


class Teeth:
    def __init__(self):
        self.src_image = 0
        self.src_gray_image = 0
        self.dst_all_mark = 0
        self.dst_fill_mark = 0
        self.dst_other_mark = 0
        self.site = (0, 0)
        self.radius = 0
        self.img_info = Img_info()

    # / *清除私有成员数据 * /
    def clear(self):
        print("clear data")

    # / *读取照片 * /
    def read_image(self, image_path):
        self.src_image = cv2.imread(image_path)

    # / *调整图片大小 * /
    def resize(self, set_rows, set_cols):
        img_rows, img_cols = self.src_image.shape[:2]

        if img_rows >= img_cols and img_rows > set_rows:
            resize_k = set_rows / img_rows
            self.src_image = cv2.resize(self.src_image, (int(resize_k*img_cols), set_rows), interpolation=cv2.INTER_AREA)
        elif img_cols > img_rows and img_cols > set_cols:
            resize_k = set_cols / img_cols
            self.src_image = cv2.resize(self.src_image, (set_cols, int(resize_k*img_rows)), interpolation=cv2.INTER_AREA)

        # 二值化
        self.src_gray_image = cv2.cvtColor(self.src_image, cv2.COLOR_BGR2GRAY)
        self.dst_all_mark = np.zeros(self.src_image.shape[:2], np.uint8)
        self.dst_fill_mark = np.zeros(self.src_image.shape[:2], np.uint8)
        self.dst_other_mark = np.zeros(self.src_image.shape[:2], np.uint8)

    # / * hsv过滤图片到bin * /
    def filter_to_bin(self):
        hsv_image = cv2.cvtColor(self.src_image, cv2.COLOR_BGR2HSV)
        img_rows, img_cols = hsv_image.shape[:2]

        for r in range(0, img_rows):
            for c in range(0, img_cols):
                if (5 <= hsv_image[r, c][0] <= 120) and \
                   (5 <= hsv_image[r, c][1] <= 200) and \
                   (50 <= hsv_image[r, c][2] <= 255):
                    self.dst_all_mark[r, c] = 255

        self.dst_all_mark = my_erode_dilate(self.dst_all_mark, 2, 6, (5, 5))

        for r in range(0, img_rows):
            for c in range(0, img_cols):
                if self.dst_all_mark[r, c] == 255:
                    if ((50 <= self.src_image[r, c][2] <= 220) or (50 <= self.src_image[r, c][1] <= 220) or(50 <= self.src_image[r, c][0] <= 220)) and \
                       (self.src_image[r, c][0] <= self.src_image[r, c][2] and self.src_image[r, c][0] <= self.src_image[r, c][1]):
                        pass
                    else:
                        self.dst_all_mark[r, c] = 0
        self.dst_all_mark = my_fill_hole(self.dst_all_mark)

    # / *将二值化图映射到原图 * /
    def bin_to_rgb(self, bin_img):
        img_rows, img_cols = bin_img.shape[:2]
        re_dst_image = np.zeros(self.src_image.shape, np.uint8)

        for r in range(0, img_rows):
            for c in range(0, img_cols):
                if bin_img[r, c] == 255:
                    re_dst_image[r, c] = self.src_image[r, c]

        return re_dst_image

    # / *分割单个患牙 * /
    def find_fill_teeth(self, site, radius):
        min_row = int(my_limit(site[0] - radius, 0, self.src_image.shape[0]))
        max_row = int(my_limit(site[0] + radius, 0, self.src_image.shape[0]))
        min_col = int(my_limit(site[1] - radius, 0, self.src_image.shape[1]))
        max_col = int(my_limit(site[1] + radius, 0, self.src_image.shape[1]))

        roi_img = self.src_image[min_row:max_row, min_col:max_col]
        row, col = roi_img.shape[:2]

        # unet获得目标牙齿的bin
        roi_img = cv2.resize(roi_img, (256, 256))
        mark_bin = unet_extract_fillteeth(roi_img)
        mark_bin = cv2.resize(mark_bin, (col, row))

        # 将roi图转换到全图
        self.dst_fill_mark[min_row:max_row, min_col:max_col] = mark_bin

    # / *将全部牙齿与单个患牙相减，得到除患牙外的其他牙齿 * /
    def find_other_teeth(self, all_mark, fill_mark):
        img_rows, img_cols = all_mark.shape[:2]
        other = copy.deepcopy(all_mark)
        for r in range(0, img_rows):
            for c in range(0, img_cols):
                if fill_mark[r, c] != 0:
                    other[r, c] = 0
        return other

    # / *提取照片中的全部牙齿 * /
    def extract_all_teeth(self):
        self.filter_to_bin()

        # 大津阈值
        src_img_copy = self.bin_to_rgb(self.dst_all_mark)
        thr = my_otsu_hsv(self.src_image, 0, 20)
        self.dst_all_mark = my_threshold_hsv(src_img_copy, thr)
        self.dst_all_mark = my_fill_hole(self.dst_all_mark)
        # self.dst_all_mark = my_erode_dilate(self.dst_all_mark, 4, 4, (5, 5))

        # 仅保存最大轮廓
        img, contours, hierarchy = cv2.findContours(self.dst_all_mark.copy(),
                                                    cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            maxcnt = max(contours, key=lambda x: cv2.contourArea(x))
            mark_filted = np.zeros(self.dst_all_mark.shape[0:2], dtype=np.uint8)
            cv2.drawContours(mark_filted, [maxcnt], -1, 255, -1)
            self.dst_all_mark = mark_filted

    # / *提取所有需要的牙齿，包括单个患牙，全部牙齿，其他牙齿 * /
    def extract_all(self, current_path, img_name):
        img_path = os.path.join(current_path, img_name)
        txt_path = os.path.join(current_path, "site.txt")

        self.clear()
        self.read_image(img_path)
        self.resize(TEETH_IMAGE_SET_ROW, TEETH_IMAGE_SET_ROW)

        self.get_fill_teeth_site(txt_path, self.img_info.operation_time)
        self.extract_all_teeth()
        self.find_fill_teeth(self.site, self.radius)

        temp_fill_bin = my_erode_dilate(self.dst_fill_mark, 0, 2, (10, 10))

        self.dst_other_mark = self.find_other_teeth(self.dst_all_mark, temp_fill_bin)

        # 调试获取坐标
        # cv2.imshow("image", self.src_image)
        # cv2.moveWindow('image', 0, 0)
        # cv2.setMouseCallback('image', self.get_roi)

    # / *根据site.txt文件过得所补牙位置信息 * /
    def get_fill_teeth_site(self, txt_path, time):
        try:
            f = open(txt_path)
        except IOError:
            print("缺少必要文件 site.text")
            return
        site_str = f.read()
        site_str = site_str.split(",\n")

        if time == '术前':
            str_temp = site_str[0].split()
            self.site = (int(str_temp[0]), int(str_temp[1]))
            self.radius = int(str_temp[2])
        elif time == '术中':
            str_temp = site_str[1].split()
            self.site = (int(str_temp[0]), int(str_temp[1]))
            self.radius = int(str_temp[2])
        elif time == '术后':
            str_temp = site_str[2].split()
            self.site = (int(str_temp[0]), int(str_temp[1]))
            self.radius = int(str_temp[2])

        f.close()

    # / *展示最终结果照片 * /
    def img_show(self):
        fill_teeth = self.bin_to_rgb(self.dst_fill_mark)
        all_teeth = self.bin_to_rgb(self.dst_all_mark)
        other_teeth = self.bin_to_rgb(self.dst_other_mark)
        cv2.imshow("原图", self.src_image)
        cv2.imshow("fill_teeth", fill_teeth)
        cv2.imshow("all_teeth", all_teeth)
        cv2.imshow("other_teeth", other_teeth)

    # / * 获得所补牙矩形框的位置信息，调试时使用 * /
    def get_roi(self, event, x, y, flags, param):
        global label_flag
        if event == cv2.EVENT_LBUTTONDOWN:
            label_flag = 1  # 左键按下
            PointStart[0], PointStart[1] = x, y  # 记录起点位置
        elif event == cv2.EVENT_LBUTTONUP and label_flag == 1:  # 左键按下后检测弹起
            label_flag = 2  # 左键弹起
            PointEnd[0], PointEnd[1] = x, y  # 记录终点位置
            PointEnd[1] = PointStart[1] + (PointEnd[0] - PointStart[0])  # 形成正方形
            # 提取ROI
            if PointEnd[0] != PointStart[0] and PointEnd[1] != PointStart[1]:  # 框出了矩形区域,而非点
                print("row", (PointStart[1] + PointEnd[1])/2)
                print("col", (PointStart[0] + PointEnd[0])/2)
                # 获取矩形框左上角以及右下角点坐标
                PointLU = [0, 0]  # 左上角点
                PointRD = [0, 0]  # 右下角点
                # 左上角点xy坐标值均较小
                PointLU[0] = min(PointStart[0], PointEnd[0])
                PointLU[1] = min(PointStart[1], PointEnd[1])
                # 右下角点xy坐标值均较大
                PointRD[0] = max(PointStart[0], PointEnd[0])
                PointRD[1] = max(PointStart[1], PointEnd[1])
                # roi宽度
                roi_width = PointRD[0] - PointLU[0]
                print("r = %d" % (roi_width/2))

        elif event == cv2.EVENT_MOUSEMOVE and label_flag == 1:  # 左键按下后获取当前坐标, 并更新标注框
            PointEnd[0], PointEnd[1] = x, y  # 记录当前位置
            PointEnd[1] = PointStart[1] + (PointEnd[0] - PointStart[0])  # 形成正方形
            image_copy = copy.deepcopy(self.src_image)
            cv2.rectangle(image_copy, (PointStart[0], PointStart[1]), (PointEnd[0], PointEnd[1]), (0, 255, 0),
                          1)  # 根据x坐标画正方形
            cv2.imshow('image', image_copy)


# / *判断此次运行程序前，照片数目，命名是否正确 * /
def pro_require(img_names):
    jpg_num = 0
    first_flag = 0
    second_flag = 0
    third_flag = 0
    correct_img_names = [0 for i in range(3)]
    for i in range(len(img_names)):
        img_str = img_names[i].split(".")
        if img_str[1] == "jpg":
            jpg_num += 1
            img_name_str = img_str[0].split("-")
            operation_time = img_name_str[1]

            if operation_time == '术前' and first_flag == 0:
                first_flag = 1
                correct_img_names[0] = img_names[i]
            elif operation_time == '术中' and second_flag == 0:
                second_flag = 1
                correct_img_names[1] = img_names[i]
            elif operation_time == '术后' and third_flag == 0:
                third_flag = 1
                correct_img_names[2] = img_names[i]
    if first_flag == 1 and second_flag == 1 and third_flag == 1 and jpg_num == 3:
        return 1, correct_img_names
    return 0, correct_img_names


def my_limit(a, min_a, max_a):
    if a < min_a:
        a = min_a
    elif a > max_a:
        a = max_a

    return a


# 大津阈值针对HSV
def my_otsu_hsv(src_image, start, end):
    hsv_image = cv2.cvtColor(src_image, cv2.COLOR_BGR2HSV)
    img_rows, img_cols = hsv_image.shape[:2]

    pixel_count = [0 for x in range(256)]
    sum = 0
    sum_count = 0
    for r in range(0, img_rows):
        for c in range(0, img_cols):
            data = hsv_image[r, c][0]
            if start < data < end:
                pixel_count[data] += 1     # // 每个灰度级的像素数目
                sum += data                # // 灰度之和
                sum_count += 1

    pixel_pro = [0.0 for x in range(256)]
    # print(sum/sum_count)
    for i in range(256):
        pixel_pro[i] = pixel_count[i] / sum_count

    delta_max = 0
    for i in range(256):
        w0 = w1 = u0_temp = u1_temp = 0.0
        for j in range(256):
            if j <= i:  					    # //背景部分
                w0 += pixel_pro[j]			    # //背景像素比例
                u0_temp += j * pixel_pro[j]
            else:  							    # //前景部分
                w1 += pixel_pro[j]			    # //前景像素比例
                u1_temp += j * pixel_pro[j]
        if w0 != 0 and w1 != 0:
            u0 = u0_temp / w0		                # //背景像素点的平均灰度
            u1 = u1_temp / w1		                # //前景像素点的平均灰度
            delta_temp = (w0 * w1 * pow((u0 - u1), 2))
            # // 当类间方差delta_temp最大时，对应的i就是阈值T
            if delta_temp > delta_max:
                delta_max = delta_temp
                threshold = i

    return threshold


# 二值化针对HSV
def my_threshold_hsv(src_image, thr):
    hsv_image = cv2.cvtColor(src_image, cv2.COLOR_BGR2HSV)
    img_rows, img_cols = hsv_image.shape[:2]

    bin_image = np.zeros((img_rows, img_cols), np.uint8)

    for r in range(0, img_rows):
        for c in range(0, img_cols):
            data = hsv_image[r, c][0]
            if data < thr:
                bin_image[r, c] = 0
            else:
                bin_image[r, c] = 255

    return bin_image


# 填充孔洞
def my_fill_hole(bin_image):
    im_fill = bin_image.copy()
    h, w = bin_image.shape[:2]

    im_fill[0, :] = 0
    im_fill[:, 0] = 0
    im_fill[h-1, :] = 0
    im_fill[:, w-1] = 0

    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(im_fill, mask, (0, 0), 255)

    im_fill_inv = cv2.bitwise_not(im_fill)
    bin_image = bin_image | im_fill_inv

    return bin_image


def my_erode_dilate(bin_image, erode_num, dilate_num, size):
    element = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, size)

    for i in range(0, erode_num):
        bin_image = cv2.erode(bin_image, element)
    for i in range(0, dilate_num):
        bin_image = cv2.dilate(bin_image, element)

    return bin_image

    # def find_fill_teeth(self, site, radius):
    #     min_row = int(my_limit(site[0] - radius * 3, 0, self.src_image.shape[0]))
    #     max_row = int(my_limit(site[0] + radius * 3, 0, self.src_image.shape[0]))
    #     min_col = int(my_limit(site[1] - radius * 3, 0, self.src_image.shape[1]))
    #     max_col = int(my_limit(site[1] + radius * 3, 0, self.src_image.shape[1]))
    #
    #     # fill_row = max_row - min_row
    #     # fill_col = max_col - min_col
    #
    #     self.dst_fill_image = copy.deepcopy(self.src_image)
    #     sure_bg = np.zeros((self.src_image.shape[0], self.src_image.shape[1]), np.uint8)
    #     for r in range(min_row, max_row):  # 10 155
    #         for c in range(min_col, max_col):  # 70 205
    #             sure_bg[r, c] = 255
    #
    #     sure_fg = np.zeros((self.src_image.shape[0], self.src_image.shape[1]), np.uint8)
    #     for r in range(site[0]-radius, site[0]+radius):
    #         for c in range(site[1]-radius, site[1]+radius):
    #             sure_fg[r, c] = 255
    #     # cv2.imshow("sure_fg", sure_fg)
    #
    #     # 未知的区域
    #     unknow = cv2.subtract(sure_bg, sure_fg)
    #     # cv2.imshow("unknow", unknow)
    #
    #     # 标记
    #     ret, markers = cv2.connectedComponents(sure_bg)  # 将确定的背景标记为0,其他为非零整数
    #     markers = markers + 1  # 将确定的背景记为1
    #     markers[unknow == 255] = 0  # 将确未知区域标记为0
    #
    #     markers = cv2.watershed(self.dst_fill_image, markers)
    #
    #     for r in range(0, self.src_image.shape[0]):
    #         for c in range(0, self.src_image.shape[1]):
    #             if markers[r, c] != 2:
    #                 self.dst_fill_image[r, c] = [0, 0, 0]
