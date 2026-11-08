import sys

from .fees import quote
from .orders import Parcel


def main(argv):
    weight_g, zone, subtotal = argv
    print(quote(Parcel(int(weight_g), zone, int(subtotal)))["total"])


if __name__ == "__main__":
    main(sys.argv[1:])
