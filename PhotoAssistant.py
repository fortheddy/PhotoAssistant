
import os
import datetime
import shutil
import hashlib
import logging
import subprocess
import sys

import configparser
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, \
    QFileDialog, QProgressBar, QComboBox, QTextEdit, QMessageBox, QCheckBox, QTabWidget, QListWidget, QFileSystemModel, \
    QTreeView, QMenu
from PyQt5.QtWidgets import QListWidgetItem
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtCore import QThread, pyqtSignal
from send2trash import send2trash

# 配置日志记录
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# 读取配置文件
config = configparser.ConfigParser()
config.read('config.ini')


# 获取用户图片和视频文件夹路径
def get_user_pictures_folder():
    if os.name == 'nt':  # Windows 系统
        return os.path.join(os.environ['USERPROFILE'], 'Pictures')
    elif os.name == 'posix':  # macOS 或 Linux 系统
        return os.path.join(str(Path.home()), 'Pictures')
    return None


def get_user_videos_folder():
    if os.name == 'nt':  # Windows 系统
        return os.path.join(os.environ['USERPROFILE'], 'Videos')
    elif os.name == 'posix':  # macOS 或 Linux 系统
        return os.path.join(str(Path.home()), 'Movies')
    return None


# 获取用户桌面路径
def get_user_desktop_folder():
    if os.name == 'nt':  # Windows 系统
        return os.path.join(os.environ['USERPROFILE'], 'Desktop')
    elif os.name == 'posix':  # macOS 或 Linux 系统
        return os.path.join(str(Path.home()), 'Desktop')
    return None


# 获取默认路径
image_target_directory = config.get('Paths', 'image_target_directory', fallback=get_user_desktop_folder())
video_target_directory = config.get('Paths', 'video_target_directory', fallback=get_user_desktop_folder())
sd_card_directory = config.get('Paths', 'sd_card_directory', fallback='H:\\')


class CopyThread(QThread):
    progress_signal = pyqtSignal(int)
    result_signal = pyqtSignal(str)

    def __init__(self, image_target, separate_mode, video_target, sd_card, event_name, selected_dates):
        super().__init__()
        self.image_target = image_target
        self.separate_mode = separate_mode
        self.video_target = video_target
        self.sd_card = sd_card
        self.event_name = event_name
        self.selected_dates = selected_dates

    def run(self):
        # 定义图片文件的扩展名，包含更多 RAW 格式
        image_extensions = (
            '.jpg', '.jpeg', '.png', '.raw', '.nef', '.cr2', '.cr3',
            '.arw',  # 索尼 RAW 格式
            '.dng',  # 通用 RAW 格式
            '.raf',  # 富士 RAW 格式
            '.orf',  # 奥林巴斯 RAW 格式
            '.pef',  # 宾得 RAW 格式
            '.srw',  # 三星 RAW 格式
            '.x3f'  # 适马 RAW 格式
        )
        video_extensions = ('.mp4', '.avi', '.mov')

        all_files = []
        for root, dirs, files in os.walk(self.sd_card):
            logging.debug(f"Processing directory: {root}")
            for file in files:
                file_path = os.path.join(root, file)
                all_files.append(file_path)
                # 增加调试信息，输出每个文件的扩展名
                file_ext = os.path.splitext(file)[1].lower()
                logging.debug(f"Found file: {file}, extension: {file_ext}")

        total_files = len(all_files)
        copied_files = 0
        created_folders = set()

        if total_files == 0:
            self.result_signal.emit("SD 卡目录中没有可用的图片或视频文件，请检查路径。")
            return

        for file_path in all_files:
            file = os.path.basename(file_path)
            lower_file = file.lower()
            is_image = False
            is_video = False
            for ext in image_extensions:
                if lower_file.endswith(ext.lower()):
                    is_image = True
                    break
            for ext in video_extensions:
                if lower_file.endswith(ext.lower()):
                    is_video = True
                    break

            if is_image or is_video:
                try:
                    date_taken = datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y%m%d')
                    if self.selected_dates and date_taken not in self.selected_dates:
                        continue
                except Exception as e:
                    logging.error(f"Failed to get modification time for {file}: {e}")
                    continue

                if is_image:
                    target_dir = self.image_target
                    logging.debug(f"File {file} identified as an image.")
                elif is_video:
                    target_dir = self.video_target
                    logging.debug(f"File {file} identified as a video.")

                logging.debug(f"Processing file: {file}")

                # 创建包含活动名称的文件夹
                folder_name = f'{date_taken}_{self.event_name}'
                folder_path = os.path.join(target_dir, folder_name)
                if folder_path not in created_folders:
                    if not os.path.exists(folder_path):
                        try:
                            os.makedirs(folder_path)
                            logging.info(f"Created folder: {folder_path}")
                        except Exception as e:
                            logging.error(f"Failed to create folder {folder_path}: {e}")
                            continue
                    created_folders.add(folder_path)

                # 处理文件名重复情况（修改目标子文件夹路径）
                new_file_name = file
                if is_image and self.separate_mode:
                    # 根据图片格式确定目标子文件夹
                    file_ext = os.path.splitext(file)[1].lower()
                    jpg_extensions = ('.jpg', '.jpeg', '.png')
                    raw_extensions = (
                    '.raw', '.nef', '.cr2', '.cr3', '.arw', '.dng', '.raf', '.orf', '.pef', '.srw', '.x3f')

                    if file_ext in jpg_extensions:
                        target_subfolder = os.path.join(folder_path, 'JPG')
                    elif file_ext in raw_extensions:
                        target_subfolder = os.path.join(folder_path, 'RAW')
                    else:
                        # 非 JPG 和 RAW 格式，可根据需求处理，这里暂时放在主文件夹
                        target_subfolder = folder_path
                else:
                    target_subfolder = folder_path  # 视频文件或不勾选时直接放主文件夹

                if is_image and self.separate_mode:
                    if not os.path.exists(target_subfolder):
                        try:
                            os.makedirs(target_subfolder)
                            logging.info(f"Created subfolder: {target_subfolder}")
                        except Exception as e:
                            logging.error(f"Failed to create subfolder {target_subfolder}: {e}")

                new_file_path = os.path.join(target_subfolder, new_file_name)
                counter = 1
                while os.path.exists(new_file_path):
                    base_name, ext = os.path.splitext(file)
                    new_file_name = f'{base_name}_{counter}{ext}'
                    new_file_path = os.path.join(target_subfolder, new_file_name)
                    counter += 1

                # 拷贝文件并进行哈希校验
                try:
                    logging.info(f"Copying {file} to {new_file_path}")
                    shutil.copy2(file_path, new_file_path)
                    with open(file_path, 'rb') as f1, open(new_file_path, 'rb') as f2:
                        hash1 = hashlib.sha256(f1.read()).hexdigest()
                        hash2 = hashlib.sha256(f2.read()).hexdigest()
                        if hash1 != hash2:
                            logging.error(f'哈希校验失败: {file}')
                        else:
                            logging.info(f'成功拷贝: {file}')
                except Exception as e:
                    logging.error(f'拷贝文件时出错: {file}, 错误信息: {e}')

            copied_files += 1
            progress = int((copied_files / total_files) * 100)
            self.progress_signal.emit(progress)

        # 确保进度条达到 100%
        self.progress_signal.emit(100)

        result_msg = f"拷贝完成，生成的文件夹有：{', '.join(created_folders)}"
        self.result_signal.emit(result_msg)


# 修改基类为 QTreeView
class CustomTreeView(QTreeView):
    def __init__(self, model):
        super().__init__()
        self.setModel(model)
        self.setContextMenuPolicy(3)  # 3 表示 CustomContextMenu
        self.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, pos):
        index = self.indexAt(pos)
        if index.isValid():
            path = self.model().filePath(index)
            menu = QMenu(self)
            open_action = menu.addAction("在文件管理器中打开")
            action = menu.exec_(self.viewport().mapToGlobal(pos))
            if action == open_action:
                self.open_path_in_file_manager(path)

    def open_path_in_file_manager(self, path):
        try:
            if sys.platform.startswith('win'):
                os.startfile(path)
            elif sys.platform.startswith('darwin'):
                subprocess.call(('open', path))
            elif sys.platform.startswith('linux'):
                subprocess.call(('xdg-open', path))
        except Exception as e:
            print(f"打开 {path} 时出错: {e}")


class FileBrowserTab(QWidget):
    def __init__(self):
        super().__init__()
        self.selected_dir = ""
        self.initUI()

    def initUI(self):
        # 路径选择框
        self.path_button = QPushButton("选择根目录")
        self.path_button.clicked.connect(self.select_root_path)
        self.path_label = QLabel(r"D:\照片\EOS R50")
        # 增大按钮高度和字体
        self.path_button.setMinimumHeight(40)
        self.path_button.setFont(QFont('Microsoft YaHei', 12))
        # 优化按钮样式
        self.path_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: 2px solid #1976D2;
                border-radius: 8px;
                padding: 8px 16px;
                box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
                box-shadow: 1px 1px 3px rgba(0, 0, 0, 0.2);
            }
        """)

        # 左侧文件系统浏览
        self.file_system_model = QFileSystemModel()
        # 设置根目录为 D:\照片\EOS R50
        root_path = self.path_label.text()
        self.file_system_model.setRootPath(root_path)
        self.tree_view = CustomTreeView(self.file_system_model)
        self.tree_view.setRootIndex(self.file_system_model.index(root_path))
        self.tree_view.clicked.connect(self.on_directory_clicked)
        # 增加树视图高度
        self.tree_view.setMinimumHeight(400)

        # 右侧显示信息
        self.jpg_count_label = QLabel("JPG 文件数量: 0")
        self.cr3_count_label = QLabel("CR3 文件数量: 0")
        self.unmatched_cr3_list = QListWidget()
        self.unmatched_cr3_label = QLabel("没有同名 JPG 文件的 CR3 文件")
        # 增加列表高度
        self.unmatched_cr3_list.setMinimumHeight(300)

        # 删除按钮
        self.delete_button = QPushButton("删除不存在同名 JPG 的 CR3 文件")
        self.delete_button.clicked.connect(self.delete_unmatched_cr3_files)
        # 增大按钮高度和字体
        self.delete_button.setMinimumHeight(40)
        self.delete_button.setFont(QFont('Microsoft YaHei', 12))
        # 使用红色系按钮样式，警示用户
        self.delete_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: 2px solid #d32f2f;
                border-radius: 8px;
                padding: 8px 16px;
                box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:pressed {
                background-color: #c62828;
                box-shadow: 1px 1px 3px rgba(0, 0, 0, 0.2);
            }
        """)

        # 选择目标路径按钮
        self.select_dir_button = QPushButton("选择目标路径")
        self.select_dir_button.clicked.connect(self.select_target_directory)

        # 显示所选路径的标签
        self.selected_dir_label = QLabel("未选择目标路径")
        # 增加按钮高度
        self.select_dir_button.setMinimumHeight(30)
        # 增加标签高度
        self.selected_dir_label.setMinimumHeight(30)

        # 执行剪切操作按钮
        self.cut_button = QPushButton("移动到所选目录")
        self.cut_button.clicked.connect(self.cut_unmatched_cr3_files)
        # 增加按钮高度
        self.cut_button.setMinimumHeight(30)

        # 打开所选路径按钮
        self.open_selected_dir_button = QPushButton("打开目标目录")
        self.open_selected_dir_button.clicked.connect(self.open_selected_directory)
        self.open_selected_dir_button.setEnabled(False)
        # 增加按钮高度
        self.open_selected_dir_button.setMinimumHeight(30)

        # 布局
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_button)
        path_layout.addWidget(self.path_label)

        left_layout = QVBoxLayout()
        left_layout.addLayout(path_layout)
        left_layout.addWidget(self.tree_view)

        right_layout = QVBoxLayout()
        right_layout.addWidget(self.jpg_count_label)
        right_layout.addWidget(self.cr3_count_label)
        right_layout.addWidget(self.unmatched_cr3_label)
        right_layout.addWidget(self.unmatched_cr3_list)
        right_layout.addWidget(self.delete_button)
        right_layout.addWidget(self.select_dir_button)
        right_layout.addWidget(self.selected_dir_label)

        right_layout.addWidget(self.cut_button)
        right_layout.addWidget(self.open_selected_dir_button)

        main_layout = QHBoxLayout()
        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)

        self.setLayout(main_layout)

    def select_root_path(self):
        root_path = QFileDialog.getExistingDirectory(self, "选择根目录")
        if root_path:
            self.path_label.setText(root_path)
            self.file_system_model.setRootPath(root_path)
            self.tree_view.setRootIndex(self.file_system_model.index(root_path))

    def on_directory_clicked(self, index):
        path = self.file_system_model.filePath(index)
        self.unmatched_cr3_list.clear()

        jpg_files = []
        cr3_files = []

        for root, dirs, files in os.walk(path):
            for file in files:
                if file.lower().endswith('.jpg'):
                    jpg_files.append(os.path.join(root, file))
                elif file.lower().endswith('.cr3'):
                    cr3_files.append(os.path.join(root, file))

        jpg_names = set([os.path.splitext(os.path.basename(jpg))[0] for jpg in jpg_files])
        unmatched_cr3 = []
        for cr3 in cr3_files:
            cr3_name = os.path.splitext(os.path.basename(cr3))[0]
            if cr3_name not in jpg_names:
                unmatched_cr3.append(cr3)

        self.jpg_count_label.setText(f"JPG 文件数量: {len(jpg_files)}")
        self.cr3_count_label.setText(f"CR3 文件数量: {len(cr3_files)}")

        for cr3 in unmatched_cr3:
            if os.path.exists(cr3):  # 检查文件路径是否存在
                item = QListWidgetItem()
                widget = QWidget()
                layout = QHBoxLayout()
                layout.setContentsMargins(0, 0, 0, 0)
                file_name = os.path.basename(cr3)
                label = QLabel(file_name)
                view_button = QPushButton("查看")
                view_button.clicked.connect(lambda _, p=cr3: self.view_single_cr3_file(p))
                layout.addWidget(label)
                layout.addWidget(view_button)

                widget.setLayout(layout)
                item.setSizeHint(widget.sizeHint())
                self.unmatched_cr3_list.addItem(item)
                self.unmatched_cr3_list.setItemWidget(item, widget)
            else:
                logging.warning(f"文件路径不存在: {cr3}")

    def view_single_cr3_file(self, cr3_path):
        if os.path.exists(cr3_path):  # 检查文件路径是否存在
            try:
                if sys.platform.startswith('win'):
                    os.startfile(cr3_path)
                elif sys.platform.startswith('darwin'):
                    subprocess.call(('open', cr3_path))
                elif sys.platform.startswith('linux'):
                    subprocess.call(('xdg-open', cr3_path))
            except Exception as e:
                print(f"打开 {cr3_path} 时出错: {e}")
        else:
            logging.warning(f"文件路径不存在: {cr3_path}")

    def cut_unmatched_cr3_files(self):
        if not self.selected_dir:
            print("未选择目标目录")
            return
        for i in range(self.unmatched_cr3_list.count()):
            item = self.unmatched_cr3_list.item(i)
            widget = self.unmatched_cr3_list.itemWidget(item)
            label = widget.findChild(QLabel)
            file_name = label.text()
            current_path = self.file_system_model.filePath(self.tree_view.currentIndex())
            for root, dirs, files in os.walk(current_path):
                if file_name in files:
                    cr3_path = os.path.join(root, file_name)
                    if os.path.exists(cr3_path):  # 检查文件路径是否存在
                        new_path = os.path.join(self.selected_dir, file_name)
                        try:
                            shutil.move(cr3_path, new_path)
                            print(f"已剪切到新目录: {cr3_path} -> {new_path}")
                        except Exception as e:
                            print(f"剪切 {cr3_path} 时出错: {e}")
                    else:
                        logging.warning(f"文件路径不存在: {cr3_path}")
        self.on_directory_clicked(self.tree_view.currentIndex())

    def delete_unmatched_cr3_files(self):
        for i in range(self.unmatched_cr3_list.count()):
            item = self.unmatched_cr3_list.item(i)
            widget = self.unmatched_cr3_list.itemWidget(item)
            label = widget.findChild(QLabel)
            file_name = label.text()
            current_path = self.file_system_model.filePath(self.tree_view.currentIndex())
            for root, dirs, files in os.walk(current_path):
                if file_name in files:
                    cr3_path = os.path.join(root, file_name)
                    # 使用原始字符串处理路径
                    cr3_path = os.path.normpath(cr3_path)
                    print(f"准备删除: {cr3_path}")
                    if os.path.exists(cr3_path):  # 检查文件路径是否存在
                        try:
                            send2trash(cr3_path)
                            print(f"已删除到回收站: {cr3_path}")
                        except Exception as e:
                            print(f"删除 {cr3_path} 时出错: {e}")
                    else:
                        logging.warning(f"文件路径不存在: {cr3_path}")
        self.on_directory_clicked(self.tree_view.currentIndex())

    def select_target_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择目标目录")
        if directory:
            self.selected_dir = directory
            self.selected_dir_label.setText(f"目标路径: {directory}")
            self.open_selected_dir_button.setEnabled(True)

    def open_selected_directory(self):
        if self.selected_dir and os.path.exists(self.selected_dir):
            try:
                if sys.platform.startswith('win'):
                    os.startfile(self.selected_dir)
                elif sys.platform.startswith('darwin'):
                    subprocess.call(('open', self.selected_dir))
                elif sys.platform.startswith('linux'):
                    subprocess.call(('xdg-open', self.selected_dir))
            except Exception as e:
                print(f"打开 {self.selected_dir} 时出错: {e}")
        else:
            print("目标目录不存在或未选择有效目录")


class CopyTab(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        # 设置窗口背景颜色为浅灰色，提升整体质感
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(245, 245, 245))
        self.setPalette(palette)

        # 图片目标目录选择
        image_layout = QHBoxLayout()
        image_label = QLabel('图片目标目录:')
        # 增大字体并设置为粗体
        image_label.setFont(QFont('Microsoft YaHei', 12, QFont.Bold))
        self.image_input = QLineEdit(image_target_directory)
        self.image_input.setFont(QFont('Microsoft YaHei', 12))
        image_button = QPushButton('选择目录')
        image_button.setFont(QFont('Microsoft YaHei', 12))
        # 优化按钮样式，添加阴影效果
        image_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: 2px solid #45a049;
                border-radius: 8px;
                padding: 8px 16px;
                box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3e8e41;
                box-shadow: 1px 1px 3px rgba(0, 0, 0, 0.2);
            }
        """)
        image_button.clicked.connect(self.select_image_directory)
        image_layout.addWidget(image_label)
        image_layout.addWidget(self.image_input)
        image_layout.addWidget(image_button)

        # 是否将RAW和JPG复制到不同的目录
        checkbox_layout = QHBoxLayout()

        checkbox_label = QLabel('将RAW和JPG复制到不同的目录：')
        checkbox_label.setFont(QFont('Arial', 12))

        self.separate_mode = QCheckBox()
        self.separate_mode.setChecked(True)
        self.separate_mode.stateChanged.connect(self.update_mode)

        checkbox_layout.addWidget(checkbox_label)
        checkbox_layout.addWidget(self.separate_mode)

        # 视频目标目录选择
        video_layout = QHBoxLayout()
        video_label = QLabel('视频目标目录:')
        video_label.setFont(QFont('Arial', 12))
        self.video_input = QLineEdit(video_target_directory)
        self.video_input.setFont(QFont('Arial', 12))
        video_button = QPushButton('选择目录')
        video_button.setFont(QFont('Arial', 12))
        video_button.setStyleSheet(
            "QPushButton { background-color: #05B8CC; color: white; border: none; border-radius: 5px; padding: 5px 10px; }"
            "QPushButton:hover { background-color: #0497AB; }")
        video_button.clicked.connect(self.select_video_directory)
        video_layout.addWidget(video_label)
        video_layout.addWidget(self.video_input)
        video_layout.addWidget(video_button)

        # SD 卡目录选择
        sd_layout = QHBoxLayout()
        sd_label = QLabel('SD 卡目录:')
        sd_label.setFont(QFont('Arial', 12))
        self.sd_input = QLineEdit(sd_card_directory)
        self.sd_input.setFont(QFont('Arial', 12))
        sd_button = QPushButton('选择目录')
        sd_button.setFont(QFont('Arial', 12))
        sd_button.setStyleSheet(
            "QPushButton { background-color: #05B8CC; color: white; border: none; border-radius: 5px; padding: 5px 10px; }"
            "QPushButton:hover { background-color: #0497AB; }")
        sd_button.clicked.connect(self.select_sd_directory)
        sd_layout.addWidget(sd_label)
        sd_layout.addWidget(self.sd_input)
        sd_layout.addWidget(sd_button)

        # 活动名称输入
        event_layout = QHBoxLayout()
        event_label = QLabel('活动名称:')
        event_label.setFont(QFont('Arial', 12))
        self.event_input = QLineEdit()
        self.event_input.setFont(QFont('Arial', 12))
        event_layout.addWidget(event_label)
        event_layout.addWidget(self.event_input)

        # 日期选择下拉框
        date_layout = QHBoxLayout()
        date_label = QLabel('选择日期:')
        date_label.setFont(QFont('Arial', 12))
        self.date_combo = QComboBox()
        self.date_combo.setFont(QFont('Arial', 12))
        # 初始就添加“全部日期”选项
        self.date_combo.addItem("全部日期")
        date_button = QPushButton('获取日期')
        date_button.setFont(QFont('Arial', 12))
        date_button.setStyleSheet(
            "QPushButton { background-color: #05B8CC; color: white; border: none; border-radius: 5px; padding: 5px 10px; }"
            "QPushButton:hover { background-color: #0497AB; }")
        date_button.clicked.connect(self.get_dates)
        date_layout.addWidget(date_label)
        date_layout.addWidget(self.date_combo)
        date_layout.addWidget(date_button)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        # 优化进度条样式，使其更美观
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #ddd;
                border-radius: 10px;
                background-color: #f3f3f3;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 8px;
                width: 20px;
            }
        """)

        # 结果显示标签，设置自动换行
        self.result_label = QLabel()
        self.result_label.setFont(QFont('Arial', 12))
        self.result_label.setWordWrap(True)

        # 开始拷贝按钮
        start_button = QPushButton('开始拷贝')
        start_button.setFont(QFont('Microsoft YaHei', 14, QFont.Bold))
        # 优化按钮样式，使用橙色系
        start_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: 2px solid #e68a00;
                border-radius: 10px;
                padding: 12px 24px;
                box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);
            }
            QPushButton:hover {
                background-color: #e68a00;
            }
            QPushButton:pressed {
                background-color: #cc7a00;
                box-shadow: 1px 1px 3px rgba(0, 0, 0, 0.2);
            }
        """)
        start_button.clicked.connect(self.start_copying)

        # 使用说明书
        instruction_text = """
使用说明：
1. 选择图片目标目录：点击“选择目录”按钮，指定图片拷贝的目标文件夹。
2. 选择视频目标目录：点击“选择目录”按钮，指定视频拷贝的目标文件夹。
3. 选择 SD 卡目录：点击“选择目录”按钮，指定 SD 卡所在的文件夹。
4. 输入活动名称：在输入框中输入本次活动的名称，用于生成文件夹名称。
5. 获取日期：点击“获取日期”按钮，程序将自动获取 SD 卡中文件的日期信息。
6. 选择日期：从下拉框中选择要拷贝的文件日期，若选择“全部日期”，将拷贝所有日期的文件。
7. 开始拷贝：点击“开始拷贝”按钮，程序将开始拷贝文件，并在进度条中显示拷贝进度。
8. 查看结果：拷贝完成后，结果将显示在下方的文本区域。
"""
        instruction_label = QTextEdit()
        instruction_label.setReadOnly(True)
        instruction_label.setFont(QFont('Arial', 10))
        instruction_label.setStyleSheet("QTextEdit { background-color: #E0E0E0; border: none; padding: 10px; }")
        instruction_label.setText(instruction_text)

        # 初始化 main_layout
        main_layout = QVBoxLayout()

        # 添加布局到主布局
        main_layout.addLayout(image_layout)
        main_layout.addLayout(checkbox_layout)
        main_layout.addLayout(video_layout)
        main_layout.addLayout(sd_layout)
        main_layout.addLayout(event_layout)
        main_layout.addLayout(date_layout)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.result_label)
        main_layout.addWidget(start_button)
        main_layout.addWidget(instruction_label)

        self.setLayout(main_layout)

    def select_image_directory(self):
        directory = QFileDialog.getExistingDirectory(self, '选择图片目标目录')
        if directory:
            self.image_input.setText(directory)

    def update_mode(self, state):
        """更新分类模式状态"""
        # 原代码这里有误，不需要重新赋值，直接使用 isChecked 方法
        pass

    def select_video_directory(self):
        directory = QFileDialog.getExistingDirectory(self, '选择视频目标目录')
        if directory:
            self.video_input.setText(directory)

    def select_sd_directory(self):
        directory = QFileDialog.getExistingDirectory(self, '选择 SD 卡目录')
        if directory:
            self.sd_input.setText(directory)

    def get_dates(self):
        sd_card = self.sd_input.text()
        image_extensions = (
            '.jpg', '.jpeg', '.png', '.raw', '.nef', '.cr2', '.CR3',
            '.arw',  # 索尼 RAW 格式
            '.dng',  # 通用 RAW 格式
            '.raf',  # 富士 RAW 格式
            '.orf',  # 奥林巴斯 RAW 格式
            '.pef',  # 宾得 RAW 格式
            '.srw',  # 三星 RAW 格式
            '.x3f'  # 适马 RAW 格式
        )
        video_extensions = ('.mp4', '.avi', '.mov')
        dates = set()
        for root, dirs, files in os.walk(sd_card):
            for file in files:
                lower_file = file.lower()
                is_image = any(lower_file.endswith(ext.lower()) for ext in image_extensions)
                is_video = any(lower_file.endswith(ext.lower()) for ext in video_extensions)
                if is_image or is_video:
                    file_path = os.path.join(root, file)
                    try:
                        date_taken = datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y%m%d')
                        dates.add(date_taken)
                    except Exception as e:
                        logging.error(f"Failed to get modification time for {file}: {e}")
        self.date_combo.clear()
        self.date_combo.addItem("全部日期")
        for date in sorted(dates):
            self.date_combo.addItem(date)

    def start_copying(self):
        image_target = self.image_input.text()
        separate_mode = self.separate_mode.isChecked()
        video_target = self.video_input.text()
        sd_card = self.sd_input.text()
        event_name = self.event_input.text()
        selected_date = self.date_combo.currentText()
        if selected_date == "全部日期":
            selected_dates = []
        else:
            selected_dates = [selected_date]

        self.copy_thread = CopyThread(image_target, separate_mode, video_target, sd_card, event_name, selected_dates)
        self.copy_thread.progress_signal.connect(self.update_progress)
        self.copy_thread.result_signal.connect(self.show_result)
        self.copy_thread.start()

    def update_progress(self, progress):
        self.progress_bar.setValue(progress)

    def show_result(self, result):
        if "SD 卡目录中没有可用的图片或视频文件" in result:
            QMessageBox.warning(self, "警告", result)
        else:
            self.result_label.setText(result)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('摄影师助手')
        self.setGeometry(300, 300, 1000, 700)

        tab_widget = QTabWidget()

        copy_tab = CopyTab()
        file_browser_tab = FileBrowserTab()

        tab_widget.addTab(copy_tab, "SD 卡拷贝")
        tab_widget.addTab(file_browser_tab, "废片清理")

        layout = QVBoxLayout()
        layout = QVBoxLayout()
        layout.addWidget(tab_widget)
        self.setLayout(layout)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
