import model_watcher
import billing
model_watcher._download_model(
    'http://10.124.228.84:8000/model/download',
    'models/current.eim'
)
print('Model updated')