FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home workspace && mkdir /data && chown workspace:workspace /data
COPY --chown=workspace:workspace . .
USER workspace
ENV APP_ENV=production DATA_DIR=/data PORT=8080
EXPOSE 8080
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:application"]
