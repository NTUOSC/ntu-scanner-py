# NTUScannerPy

Scanner used in NTUSC election 106-1, written using PyGObject.

<p align="center">
<img src="screenshots/01-auth-code.png" alt="01">
<img src="screenshots/02-idle.png" alt="02">
<img src="screenshots/03-manually-input.png" alt="03">
<img src="screenshots/04-failure-voted.png" alt="04">
<img src="screenshots/05-success-final.png" alt="05">
</p>

# Installing

> Pre-built Glade 3.20.2 with source (Linux x86-64): https://www.dropbox.com/s/38mefvlw4h5s5vz/glade.zip?dl=0

## Installation kit

1. Python 安裝包 (3.4 以下，32-bit)
2. [PyGObject on Windows](https://sourceforge.net/projects/pygobjectwin32/) (Latest: GIO 3.24.1, **GTK+ 3.18**) \
   安裝的時候要記得勾選 GTK+ 這個 dependency
3. pip dependencies (for offline)
4. 讀卡機函式庫：dcrf32.dll
5. 主程式 (*.py or *.pyc)
6. Glade UI file + CSS assets \
   注意 Glade 內要調整 UI 的相容性至 3.18 而非預設的 3.20
