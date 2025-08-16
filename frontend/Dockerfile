# Use the official nginx image from Docker Hub
FROM nginx:alpine

# Remove the default nginx website
RUN rm -rf /usr/share/nginx/html/*

# Copy the new nginx configuration file
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy the static assets to the nginx image
COPY ./src /usr/share/nginx/html

# The container will expose port 80
EXPOSE 80
