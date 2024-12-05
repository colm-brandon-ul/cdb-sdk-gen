# cdb-sdk-gen

Repository for the cinco-de-bio domain-specific SDK code generator.

## Introduction

The `cdb-sdk-gen` project is designed to generate a domain-specific SDK for the 'cinco-de-bio' domain. It leverages Python and Jinja templates to automate the creation of SDKs.

## Installation

To install the required dependencies, you can use the following command:

```sh
pip install -r requirements.txt
```

## Dependencies

The project relies on the following Python packages:
- jinja2
- rdflib
- matplotlib
- networkx
- requests
- black
- build

## Usage

To use the `cdb-sdk-gen`, follow the instructions below:

1. Clone the repository:
   ```sh
   git clone https://github.com/colm-brandon-ul/cdb-sdk-gen.git
   ```
2. Install Dependencies:
   ```sh
      # you should create a venv and activate it before doing this.
      pip install -r requirements.txt
   ```
3. Run the SDK generator:
   ```sh
   python src/sdkgen.py <ontology-url>
   ```

## Recent Changes

Check the [commit history](https://github.com/colm-brandon-ul/cdb-sdk-gen/commits/main) for recent updates and changes to the project.

## Contributing

If you wish to contribute to this project, please follow the standard GitHub workflow: fork the repository, create a new branch, make your changes, and submit a pull request.

