const { defineConfig } = require('@vue/cli-service')
const path = require('path')

module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true
      }
    }
  },
  configureWebpack: {
    experiments: {
      asyncWebAssembly: true
    },
    resolve: {
      extensions: ['.ts', '.js', '.vue', '.json'],
      alias: {
        '@': path.resolve(__dirname, 'src'),
        '@/ws-scrcpy': path.resolve(__dirname, 'src/ws-scrcpy')
      },
      fallback: {
        "path": require.resolve("path-browserify"),
        "buffer": require.resolve("buffer"),
        "fs": false,
        "crypto": false,
        "stream": false,
        "util": false,
        "url": false,
        "zlib": false,
        "http": false,
        "https": false,
        "assert": false,
        "os": false,
        "querystring": false,
        "env": false
      }
    },
    module: {
      rules: [
        {
          test: /\.ts$/,
          use: [
            {
              loader: 'babel-loader',
              options: {
                presets: [
                  ['@babel/preset-env', { targets: "defaults" }],
                  '@babel/preset-typescript'
                ]
              }
            }
          ],
          exclude: /node_modules/
        },
        {
          test: /\.wasm$/,
          type: 'webassembly/async'
        },
        {
          test: /\.asset$/,
          type: 'webassembly/async'
        },
        {
          test: /\.svg$/,
          type: 'asset/source'
        }
      ]
    },
    plugins: [
      new (require('webpack')).ProvidePlugin({
        Buffer: ['buffer', 'Buffer'],
      })
    ],
    devtool: 'source-map',
    output: {
      devtoolModuleFilenameTemplate: info => {
        const resourcePath = info.resourcePath
        if (resourcePath.match(/\.(vue|js|ts)$/)) {
          return `webpack:///${resourcePath}?${info.hash}`
        }
        return `webpack:///${resourcePath}`
      }
    }
  }
})