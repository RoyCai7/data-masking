FROM node:20-alpine as builder

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy source files
COPY . .

# Build the application
RUN npm run build

# Production image — use unprivileged nginx
FROM nginxinc/nginx-unprivileged:alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
