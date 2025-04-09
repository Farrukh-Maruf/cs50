from cs50 import get_float
def get_float(prompt):
    while True:
        try:
            value = float(input(prompt))
            return value
        except ValueError:
            pass  

def main():
    while True:
        change_owed = get_float("Change owed: ")
        if change_owed >= 0:
            break
    
    cents = round(change_owed * 100)
    
    coins = [25, 10, 5, 1]  # quarters, dimes, nickels, pennies
    
    # Calculate minimum number of coins
    coin_count = 0
    for coin in coins:
        coin_count += cents // coin
        cents %= coin
    
    print(coin_count)

if __name__ == "__main__":
    main()