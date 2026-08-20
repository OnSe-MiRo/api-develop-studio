FROM node:22-alpine

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ARG NPM_PROXY
ARG NPM_HTTPS_PROXY
ARG NPM_REGISTRY
ARG NPM_STRICT_SSL

ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    NO_PROXY=${NO_PROXY} \
    http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    no_proxy=${NO_PROXY} \
    npm_config_proxy=${NPM_PROXY} \
    npm_config_https_proxy=${NPM_HTTPS_PROXY} \
    npm_config_registry=${NPM_REGISTRY} \
    npm_config_strict_ssl=${NPM_STRICT_SSL}

WORKDIR /app

COPY package.json package-lock.json ./

# npm reads the npm_config_* values above while installing dependencies.
RUN npm ci

COPY . ./

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
