# Use a basic Python image
FROM python:3.6.4

WORKDIR /reference_parser


COPY ./models/ /reference_parser/models

COPY ./utils/__init__.py /reference_parser/utils/__init__.py
COPY ./utils/file_manager.py /reference_parser/utils/file_manager.py
COPY ./utils/fuzzymatch.py /reference_parser/utils/fuzzymatch.py
COPY ./utils/predict.py /reference_parser/utils/predict.py
COPY ./utils/s3.py /reference_parser/utils/s3.py
COPY ./utils/separate.py /reference_parser/utils/separate.py
COPY ./utils/serialiser.py /reference_parser/utils/serialiser.py

COPY ./main.py /reference_parser/main.py
COPY ./models.py /reference_parser/models.py
COPY ./settings.py /reference_parser/settings.py

COPY ./requirements.txt /reference_parser/requirements.txt
RUN pip install -r requirements.txt

CMD ["python", "main.py"]
