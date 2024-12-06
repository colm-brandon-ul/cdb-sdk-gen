import pathlib
import os
import json
import re
import click

from ._cli_utils import ServiceParser, TestGenerator, init_service_directory, delete_cdb_labaels_with_regex
from .__init__ import __library_name__, __detailed_version__
from ._config import Config

@click.group()
def cli():
    ...

@cli.command()
@click.argument("file", type=click.Path())
@click.option("--tests", is_flag=True, help="Attempt to generate tests for the service.")
def eval(file,tests):
    # This function as the CLI entrpy point for the cellmaps-sdk, which is used to verify and extract the schema from a dataprocessing service file.

    # Define Refex pattern for clear old cincodebio labels
    regex = re.compile(r"LABEL cincodebio\.schema='.*'' \\ \n cincodebio\.ontology_version='.*'")

    # set the debug flag to True

    Config._DEBUG = True

    # Check if the filepath is absolute or relative
    if os.path.isabs(file):
        # check if file exists
        if not pathlib.Path(file).exists():
            raise FileNotFoundError(f"The file {file} does not exist")
    # case where path is relative
    else:
        # get the current working directory
        cwd = os.getcwd()
        # join the cwd with the relative path to get the absolute path
        absolute_path = os.path.join(cwd, file)
        # check if file exists
        if not pathlib.Path(absolute_path).exists():
            raise FileNotFoundError(f"The file {absolute_path} does not exist")
        
        # set the absolute path to the filepath
        file = absolute_path

    # Create a ServiceParser object
    service_parser = ServiceParser()
    dps_schema = (service_parser.get_schema(
        file_name=file
    ))

    
    # Read original dockerfile and remove old cincodebio labels
    delete_cdb_labaels_with_regex(pathlib.Path(os.getcwd()) / "Dockerfile")

    # Add the new cincodebio labels
    with open(pathlib.Path(os.getcwd()) / "Dockerfile", 'a') as df:
        df.write(f"\nLABEL cincodebio.schema='{json.dumps(dps_schema)}' \ \n cincodebio.ontology_version='{__library_name__}~{__detailed_version__}'")

    if tests:
        tg = TestGenerator(dataclass_schemas=dps_schema)
        tg.generate_tests()

@cli.command()
def version():
    click.echo(f"{__library_name__} version {__detailed_version__}")


def validate_service_name(ctx, param, value):
    if not re.match(r'^[A-Z][a-zA-Z0-9]*$', value):
        raise click.BadParameter('service_name must use UpperCamelCase.')
    return value

def validate_python_version(ctx, param, value):
    if value is None:
        return value
    if not re.match(r'^\d+\.\d+$', value):
        raise click.BadParameter('python_version must be a string in the form of X.Y.')
    return value

def validate_base_docker_image(ctx, param, value):
    if value is None:
        return value
    if not re.match(r'^[a-z0-9-]+:[a-z0-9-]+$', value):
        raise click.BadParameter('base_docker_image must be a string in the form of image:tag.')
    return value

def validate_process_concept(ctx, param, value):
    # should be populate from process_concepts
    if not re.match(r'^[A-Z][a-zA-Z0-9]*$', value):
        raise click.BadParameter('ProcessConcept must use UpperCamelCase.')
    return value

@cli.command()
@click.argument("service_name", callback=validate_service_name)
@click.argument("process_concept", callback=validate_process_concept)
@click.option("--python_version", default=None, callback=validate_python_version, help="Python version in the form of X.Y. Default Image is python-slim. If not provided, a Docker image must be provided.")
@click.option("--docker_image", default=None, callback=validate_base_docker_image, help="Base Docker image in the form of image:tag.")
@click.option("--automated", is_flag=True, help="Create an automated service.")
@click.option("--interactive", is_flag=True, help="Create an interactive service. With a front-end")
def init(service_name,process_concept,python_version,docker_image, automated, interactive):
    if automated and interactive:
        click.echo("Error: Cannot use both --automated and --interactive options at the same time.", err=True)
        return

    if not automated and not interactive:
        click.echo("Error: Must specify either --automated or --interactive option.", err=True)
        return
    
    if not python_version and not docker_image:
        click.echo("Error: Must specify either python_version or docker_image.", err=True)
        return
    

    if automated:
        click.echo("Initializing service directory...")
        init_service_directory(service_name,process_concept, False, python_version, docker_image)

    elif interactive:
        click.echo("Initializing service directory...")
        init_service_directory(service_name, process_concept, True, python_version, docker_image)


if __name__ == "__main__":
    cli()