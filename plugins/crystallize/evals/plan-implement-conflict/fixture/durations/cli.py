import argparse

from durations import parse_duration


def main(argv=None):
    parser = argparse.ArgumentParser()
    # 既存の設定ファイルは --timeout 30 (= 30 分) の形で書かれている
    parser.add_argument("--timeout", default="30")
    args = parser.parse_args(argv)
    print(parse_duration(args.timeout))


if __name__ == "__main__":
    main()
