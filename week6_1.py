def pyramid(height):
    for i in range(1, height+1):
        spaces = height - i
        column = i
        print( ' ' * spaces + '#' * column + ' '+ '#' * column + ' ' * spaces)
def main():
    while True:
        try:
            user = input("Height: ")
            number = int(user)

            if number <=0 :
                print('input ony number greater than 0')
                continue
            if number is None:
                print('write number:')
            
            pyramid(number)
        except ValueError:
             print('son yozing:')
             continue

if __name__ == "__main__":
   main()