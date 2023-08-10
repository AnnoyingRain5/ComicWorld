FROM tecktron/python-waitress:latest

COPY ./ /app

EXPOSE 80
ENV APP_MODULE="app:app"
VOLUME /app/db/
VOLUME /app/static/comics/

RUN pip install -r /app/requirements.txt
