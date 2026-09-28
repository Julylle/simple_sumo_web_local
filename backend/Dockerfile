FROM mambaorg/micromamba:2.9.0

COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml /tmp/environment.yml
RUN micromamba install --yes --name base --file /tmp/environment.yml && \
    micromamba clean --all --yes

ARG MAMBA_DOCKERFILE_ACTIVATE=1
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt && python -m pip check
COPY --chown=$MAMBA_USER:$MAMBA_USER . .
RUN python -c "import math; from assimulo.problem import Explicit_Problem; from assimulo.solvers import CVode; solver = CVode(Explicit_Problem(lambda t, y: -y, [1.0], 0.0)); t, y = solver.simulate(1.0); assert abs(y[-1, 0] - math.exp(-1)) < 1e-4"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
