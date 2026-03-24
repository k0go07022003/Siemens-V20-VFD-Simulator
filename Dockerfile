FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir pymodbus==3.12.1 pyserial==3.5 flask==3.1.3

COPY v20_web.py .

EXPOSE 5000 502

ENTRYPOINT ["python", "v20_web.py", "--no-browser"]
CMD ["--tcp", "--tcp-port", "502", "--web-port", "5000"]
