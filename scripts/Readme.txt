Script descriptions:

run_exchange.py
    Creates and sends emails to the sender with receiver's address. 
    Uses history database to try and make sure no sender sends to someone they have before.


send_missing.py
    Missnamed. Used to pull users and receiver picks from the current year's submissions and history file from text file of email addresses that didn't send 
    Doesn't send anything. History file currently wrote to early in the process and will be changed to not write on error.
    Parts of this may be used in a future error handling module. I basically had to write this, with AI assistance, to get the 
    matches after the main program crashed after hitting a email sending rate limit.

server.py
    Simple webserver to handle the form submission into sqlite database. Security handled on server, not here 
    Mostly AI written.

setup_env.sh
    Initially used with smtp_test to set environment variables instead of using.env file. Obsolete.

smtp_test.py
    Sends a test email to yourself. 
    Test that environment variables loaded from the .env file work correctly for your choosen email provider.
    Will have to be tweaked to work with a different provider than I use.
