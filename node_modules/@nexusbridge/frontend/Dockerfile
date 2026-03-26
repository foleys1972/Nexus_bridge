FROM node:22-alpine
WORKDIR /app
COPY package.json ./
RUN npm install
COPY index.html vite.config.ts tsconfig.json tailwind.config.js postcss.config.js ./
COPY src ./src
EXPOSE 5173
CMD ["npm", "run", "dev"]
