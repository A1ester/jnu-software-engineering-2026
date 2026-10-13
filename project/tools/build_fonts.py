"""Build local webfonts from licensed font sources, retaining interface glyphs."""
import argparse
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

PROJECT = Path(__file__).resolve().parents[1]
TARGET = PROJECT / 'src' / 'campus_clubs' / 'static' / 'fonts'


def interface_characters():
    text = '，。！？：；（）—…·、↗‹›＋／✓◇◷▦▥☷▤⌑⚑◉≡✧禾青0123456789'
    for path in (PROJECT / 'src' / 'campus_clubs').rglob('*'):
        if path.suffix in ('.py', '.js', '.html'):
            text += path.read_text(encoding='utf-8')
    return set(range(32, 127)) | {ord(character) for character in text}


def write_subset(source, destination, unicodes):
    font = TTFont(source)
    options = subset.Options()
    options.flavor = 'woff2'
    options.layout_features = ['*']
    options.name_IDs = ['*']
    options.name_legacy = True
    options.name_languages = ['*']
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=unicodes)
    subsetter.subset(font)
    font.flavor = 'woff2'
    font.save(destination)
    font.close()
    print(destination.name, destination.stat().st_size, 'bytes')


def main():
    parser = argparse.ArgumentParser(description='生成界面本地字体；需要 fonttools 和 brotli')
    parser.add_argument('--space-grotesk', required=True, type=Path)
    parser.add_argument('--noto-sans-sc', required=True, type=Path)
    args = parser.parse_args()
    TARGET.mkdir(parents=True, exist_ok=True)
    write_subset(args.space_grotesk, TARGET / 'space-grotesk-latin.woff2', set(range(32, 127)))
    write_subset(args.noto_sans_sc, TARGET / 'noto-sans-sc.woff2', interface_characters())


if __name__ == '__main__':
    main()
