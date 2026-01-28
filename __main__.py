# The file __main__.py marks the main entry point for the application when running 
# it via runpy (i.e. python -m greetings, which works immediately with flat layout, 
# but requires installation of the package with src layout), so initialize the 
# command-line interface here:

if __name__ == "__main__":
    from main import cli
    cli()