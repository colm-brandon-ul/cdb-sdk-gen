python src/sdkgen.py https://cellmaps.colmb.me/ontology/v0.0.1/cellmaps.owl 
cd gen/src
# ruff check .
mypy --install-types
mypy -m cdb_cellmaps --show-error-codes
cd ../..