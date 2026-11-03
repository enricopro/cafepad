from setuptools import setup

setup(
    py_modules=["cafepad", "cafepad_gui", "wiiupro"],
    entry_points={
        "console_scripts": [
            "cafepad = cafepad:main",
            "cafepad-gui = cafepad_gui:main",
            "wiiupro = cafepad:main",
        ],
    },
)
