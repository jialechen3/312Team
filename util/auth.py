def validate_password(string):
    if len(string) < 8:
        return False
    specialChars = ["!", "@", "#", "$", "%", "^", "&", "(", ")", "-", "_", "="]
    allowedChars = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z", 
                    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z",
                    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"] + specialChars

    lower = upper = number = special = False

    for char in string:
        if char not in allowedChars:
            return False
        elif char.islower():
            lower = True
        elif char.isupper():
            upper = True
        elif char.isdigit():
            number = True
        elif char in specialChars:
            special = True

    return lower and upper and number and special
