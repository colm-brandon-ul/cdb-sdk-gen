python src/sdkgen.py https://cellmaps.colmb.me/ontology/v0.0.1/cellmaps.owl 
cd gen/src
# ruff check .
mypy --install-types -y
mypy -m cdb_cellmaps --strict --show-error-codes
cd ../..