FROM nginx:alpine

COPY fixdoc-web/nginx.conf /etc/nginx/templates/default.conf.template
COPY fixdoc-web/ /usr/share/nginx/html

ENV NGINX_ENVSUBST_FILTER=PORT

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
