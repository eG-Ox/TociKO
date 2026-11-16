"""Aprende de tus partidas y ejecuta una política autónoma local para Roblox."""
import argparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    rec = subs.add_parser('record', help='Grabar demostraciones de teclado y mouse relativo')
    rec.add_argument('--data', default='data')
    rec.add_argument('--fps', type=int, default=10, choices=range(1, 31))
    fit = subs.add_parser('train', help='Entrenar una política con memoria visual reciente')
    fit.add_argument('--data', default='data')
    fit.add_argument('--model', default='models/policy.pt')
    fit.add_argument('--epochs', type=int, default=10, choices=range(1, 1001))
    fit.add_argument('--batch-size', type=int, default=32, choices=range(1, 257))
    pred = subs.add_parser('predict', help='Predecir acciones para una imagen')
    pred.add_argument('image')
    pred.add_argument('--model', default='models/policy.pt')
    run = subs.add_parser('play', help='Observar y decidir; --execute activa controles reales')
    run.add_argument('--model', default='models/policy.pt')
    run.add_argument('--execute', action='store_true')
    run.add_argument('--logs', default='runs')
    run.add_argument('--threshold', type=float, default=0.55)
    run.add_argument('--mouse-scale', type=float, default=1.0)
    args = parser.parse_args()
    if args.command == 'record':
        from recorder import record
        record(args)
    elif args.command == 'train':
        from policy import train
        train(args)
    elif args.command == 'predict':
        from policy import predict
        predict(args)
    elif args.command == 'play':
        if not 0.1 <= args.threshold <= 0.99 or not 0 <= args.mouse_scale <= 3:
            parser.error('--threshold debe estar entre 0.1 y 0.99; --mouse-scale entre 0 y 3.')
        from agent import play
        play(args)


if __name__ == '__main__':
    main()
